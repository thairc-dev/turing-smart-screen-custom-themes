from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from trueview26.config import THEME_ROOT, load_config
from trueview26.metrics import MetricsCollector, MetricsSnapshot, SystemInfo
from trueview26.protocol import CLEAR, DISPLAY_BITMAP, SCREEN_OFF, build_command, image_to_rgb565le
from trueview26.renderer import cleanse_display, format_rate, format_uptime, render_session
from trueview26.transports.preview_transport import PreviewTransport
from trueview26.weather import WeatherCollector, compact_condition


class StaticMetrics(MetricsCollector):
    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            cpu_percent=31,
            per_core=(20, 40, 30, 50),
            cpu_frequency_ghz=4.0,
            cpu_temp_c=72,
            gpu_percent=38,
            gpu_temp_c=68,
            ram_percent=80,
            ram_used_gb=12.8,
            ram_total_gb=16,
            disk_percent=91,
            disk_used_gb=223,
            disk_total_gb=245,
            net_up_mb_s=12.4,
            net_down_mb_s=38.1,
            network_interface="en1",
            load_average_1m=1.24,
            process_count=198,
            fan_rpm=2188,
            uptime_seconds=3 * 86400 + 14 * 3600 + 26 * 60,
            warning=True,
            health_status="DISK",
            health_line1="Free space",
            health_line2="running low",
        )


class TrueView26Tests(unittest.TestCase):
    def test_command_encoding(self) -> None:
        command = build_command(DISPLAY_BITMAP, 12, 44, 240, 240)
        self.assertEqual(len(command), 6)
        self.assertEqual(command[-1], DISPLAY_BITMAP)

    def test_rgb565_size(self) -> None:
        image = Image.new("RGB", (13, 7), "white")
        self.assertEqual(len(image_to_rgb565le(image)), 13 * 7 * 2)

    def test_config_paths_are_relative_to_theme(self) -> None:
        config = load_config()
        self.assertEqual(config.assets_dir, THEME_ROOT)
        self.assertEqual(config.fonts_dir, THEME_ROOT / "fonts")

    def test_dynamic_values_compact_at_layout_boundaries(self) -> None:
        self.assertEqual(format_rate(12.44), "12.4")
        self.assertEqual(format_rate(1234), "1.2K")
        self.assertEqual(format_uptime(1000 * 86400), "2.7y 0h")

    def test_weather_descriptions_are_meaningful_and_fit(self) -> None:
        self.assertEqual(compact_condition("Partly cloudy"), ("PARTLY CLOUDY", "partly_cloudy"))
        self.assertEqual(compact_condition("Light rain shower"), ("RAIN", "rain"))

    def test_startup_cleanse_ends_on_full_black_frame(self) -> None:
        display = PreviewTransport()
        with patch("trueview26.renderer.time.sleep"):
            cleanse_display(display, chunk_size=4096)
        self.assertEqual(display.writes[0][-1], SCREEN_OFF)
        self.assertTrue(any(len(payload) == 6 and payload[-1] == CLEAR for payload in display.writes))
        self.assertEqual(
            sum(len(payload) == 6 and payload[-1] == DISPLAY_BITMAP for payload in display.writes),
            1,
        )
        self.assertEqual(display.image.getbbox(), None)

    def test_preview_is_complete_frame(self) -> None:
        config = load_config()
        display = PreviewTransport()
        weather = WeatherCollector(config.weather)
        with tempfile.TemporaryDirectory() as directory:
            render_session(
                config,
                display,
                StaticMetrics(),
                weather,
                SystemInfo("apple", "Mac mini M4", "macOS 26.4.1"),
                threading.Event(),
                max_frames=1,
            )
            output = Path(directory) / "preview.png"
            display.save(output)
            with Image.open(output) as preview:
                self.assertEqual(preview.size, (480, 320))
            self.assertGreater(output.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
