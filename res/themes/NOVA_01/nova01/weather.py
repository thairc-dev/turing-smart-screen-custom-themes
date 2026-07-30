from __future__ import annotations

from dataclasses import dataclass, replace
import datetime
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
    temperature: str = "32°C"
    description: str = "Partly Cloudy"
    condition: str = "partly_cloudy"
    location: str = "HO CHI MINH CITY"
    high_c: str = "33°"
    low_c: str = "26°"
    humidity: str = "65%"
    forecast_days: tuple[tuple[str, str, str, str], ...] = (
        ("WED", "rain", "32°", "25°"),
        ("THU", "cloudy", "31°", "25°"),
        ("FRI", "partly_cloudy", "33°", "26°"),
        ("SAT", "clear", "34°", "27°"),
        ("SUN", "clear", "34°", "27°"),
    )


def compact_condition(description: str) -> tuple[str, str]:
    normalized = description.strip().lower()
    if "thunder" in normalized:
        return "Thunder", "thunder"
    if "snow" in normalized or "blizzard" in normalized:
        return "Snow", "snow"
    if "sleet" in normalized or "ice" in normalized:
        return "Sleet", "snow"
    if "rain" in normalized or "shower" in normalized:
        return "Rain", "rain"
    if "drizzle" in normalized:
        return "Drizzle", "rain"
    if "fog" in normalized or "mist" in normalized:
        return "Fog", "fog"
    if "partly" in normalized:
        return "Partly Cloudy", "partly_cloudy"
    if "cloud" in normalized or "overcast" in normalized:
        return "Cloudy", "cloudy"
    if "sun" in normalized or "clear" in normalized:
        return "Clear", "clear"
    label = description.title()
    return (label if len(label) <= 16 else "Weather", "unknown")


def build_consecutive_5_days() -> tuple[tuple[str, str, str, str], ...]:
    days_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    conds = ["rain", "cloudy", "partly_cloudy", "clear", "clear"]
    temps = [("32°", "25°"), ("31°", "25°"), ("33°", "26°"), ("34°", "27°"), ("34°", "27°")]
    today = datetime.date.today()
    res = []
    for i in range(5):
        dt = today + datetime.timedelta(days=i)
        dname = days_map[dt.weekday()]
        hi, lo = temps[i % len(temps)]
        cond = conds[i % len(conds)]
        res.append((dname, cond, hi, lo))
    return tuple(res)


class WeatherCollector:
    def __init__(self, config: WeatherConfig):
        self.config = config
        self._snapshot = WeatherSnapshot(forecast_days=build_consecutive_5_days())
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.config.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="nova01-weather", daemon=True
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
            headers={"User-Agent": "NOVA01/1.0"},
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
        humidity = f"{current.get('humidity', '65')}%"

        forecast_list = []
        days_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        last_dt = datetime.date.today()

        for day_data in weather_days:
            date_str = day_data.get("date", "")
            try:
                dt = datetime.date.fromisoformat(date_str)
                last_dt = dt
                dname = days_map[dt.weekday()]
            except Exception:
                dname = days_map[last_dt.weekday()]
            
            day_high = f"{day_data.get('maxtempC', '33')}°"
            day_low = f"{day_data.get('mintempC', '25')}°"
            hourly = day_data.get("hourly", [{}])[0]
            desc_val = hourly.get("weatherDesc", [{}])[0].get("value", "")
            _, day_cond = compact_condition(desc_val)
            forecast_list.append((dname, day_cond, day_high, day_low))

        # Always fill up to 5 full consecutive days
        while len(forecast_list) < 5:
            last_dt += datetime.timedelta(days=1)
            dname = days_map[last_dt.weekday()]
            forecast_list.append((dname, "clear", "34°", "27°"))

        return WeatherSnapshot(
            temperature=f"{current['temp_C']}°C",
            description=description,
            condition=condition,
            location=location_name,
            high_c=high_c,
            low_c=low_c,
            humidity=humidity,
            forecast_days=tuple(forecast_list[:5]),
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
