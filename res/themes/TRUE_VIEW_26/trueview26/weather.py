from __future__ import annotations

from dataclasses import dataclass, replace
import json
import logging
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request

import certifi

from .config import WeatherConfig


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeatherSnapshot:
    temperature: str = "--°C"
    description: str = "NO DATA"
    condition: str = "unknown"
    location: str = ""
    high_c: str = "--°"
    low_c: str = "--°"
    humidity: str = "--%"


def compact_condition(description: str) -> tuple[str, str]:
    normalized = description.strip().lower()
    if "thunder" in normalized:
        return "THUNDER", "thunder"
    if "snow" in normalized or "blizzard" in normalized:
        return "SNOW", "snow"
    if "sleet" in normalized or "ice" in normalized:
        return "SLEET", "snow"
    if "rain" in normalized or "shower" in normalized:
        return "RAIN", "rain"
    if "drizzle" in normalized:
        return "DRIZZLE", "rain"
    if "fog" in normalized or "mist" in normalized:
        return "FOG", "fog"
    if "partly" in normalized:
        return "PARTLY CLOUDY", "partly_cloudy"
    if "cloud" in normalized or "overcast" in normalized:
        return "CLOUDY", "cloudy"
    if "sun" in normalized or "clear" in normalized:
        return "CLEAR", "clear"
    label = description.upper()
    return (label if len(label) <= 14 else "WEATHER", "unknown")


class WeatherCollector:
    def __init__(self, config: WeatherConfig):
        self.config = config
        self._snapshot = WeatherSnapshot()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.config.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="trueview26-weather", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def snapshot(self) -> WeatherSnapshot:
        with self._lock:
            return replace(self._snapshot)

    def _fetch(self) -> WeatherSnapshot:
        location = urllib.parse.quote(self.config.location, safe="")
        request = urllib.request.Request(
            f"https://wttr.in/{location}?format=j1",
            headers={"User-Agent": "TRUEVIEW26/1.0"},
        )
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(
            request, timeout=self.config.timeout_seconds, context=context
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        current = data["current_condition"][0]
        description, condition = compact_condition(
            current["weatherDesc"][0]["value"]
        )
        nearest_area = data.get("nearest_area") or []
        location_name = self.config.location.upper() or "HO CHI MINH CITY"
        if nearest_area and not self.config.location:
            names = nearest_area[0].get("areaName") or []
            if names:
                location_name = str(names[0].get("value", "")).upper()

        weather_days = data.get("weather", [])
        high_c = f"{current.get('maxtempC', '33')}°"
        low_c = f"{current.get('mintempC', '26')}°"
        if weather_days:
            high_c = f"{weather_days[0].get('maxtempC', '33')}°"
            low_c = f"{weather_days[0].get('mintempC', '26')}°"
        humidity = f"{current.get('humidity', '65')}%"

        return WeatherSnapshot(
            temperature=f"{current['temp_C']}°C",
            description=description,
            condition=condition,
            location=location_name,
            high_c=high_c,
            low_c=low_c,
            humidity=humidity,
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                snapshot = self._fetch()
                with self._lock:
                    self._snapshot = snapshot
            except (
                KeyError,
                ValueError,
                json.JSONDecodeError,
                urllib.error.URLError,
                TimeoutError,
            ) as exc:
                LOG.warning("Weather update failed: %s", exc)
            self._stop.wait(self.config.refresh_seconds)
