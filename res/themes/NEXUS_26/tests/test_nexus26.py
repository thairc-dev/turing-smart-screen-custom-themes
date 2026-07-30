from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from nexus26.config import THEME_ROOT, load_config
from nexus26.metrics import MetricsCollector, MetricsSnapshot, SystemInfo
from nexus26.protocol import DISPLAY_BITMAP, build_command, image_to_rgb565le
from nexus26.renderer import (
    draw_fan_value,
    draw_wide_center_dot_matrix_visualizer,
    format_network_rate,
    format_uptime,
    render_session,
)
from nexus26.transports.preview_transport import PreviewTransport
from nexus26.weather import WeatherCollector


class StaticMetrics(MetricsCollector):
    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            cpu_percent=32,
            per_core=(20, 40, 30, 50),
            cpu_temp_c=48,
            gpu_percent=38,
            gpu_temp_c=46,
            ram_percent=50,
            ram_used_gb=8,
            ram_total_gb=16,
            disk_percent=91,
            disk_used_gb=223,
            disk_total_gb=245,
            fan_rpm=1000,
            uptime_seconds=86400,
            warning=True,
            health_status="DISK",
            health_line1="Free space",
            health_line2="running low",
        )


class Nexus26Tests(unittest.TestCase):
    def test_command_encoding(self) -> None:
        command = build_command(DISPLAY_BITMAP, 12, 44, 240, 240)
        self.assertEqual(len(command), 6)
        self.assertEqual(command[-1], DISPLAY_BITMAP)

    def test_rgb565_size(self) -> None:
        image = Image.new("RGB", (13, 7), "purple")
        self.assertEqual(len(image_to_rgb565le(image)), 13 * 7 * 2)

    def test_four_digit_fan_value_stays_inside_card(self) -> None:
        image = Image.new("RGB", (96, 68), "black")
        draw = ImageDraw.Draw(image)
        bold = THEME_ROOT / "fonts" / "Roboto-Bold.ttf"
        regular = THEME_ROOT / "fonts" / "Roboto-Regular.ttf"
        bounds = draw_fan_value(
            draw,
            right_x=92,
            y=27,
            rpm=2188,
            value_font=ImageFont.truetype(str(bold), 14),
            unit_font=ImageFont.truetype(str(regular), 9),
            compact_font=ImageFont.truetype(str(bold), 10),
            value_color="white",
            unit_color="gray",
        )
        self.assertGreaterEqual(bounds[0], 34)
        self.assertLessEqual(bounds[1], 92)

    def test_footer_values_compact_before_they_can_overflow(self) -> None:
        self.assertEqual(format_network_rate(38.14), "38.1")
        self.assertEqual(format_network_rate(999.9), "1000")
        self.assertEqual(format_network_rate(1234.0), "1.2K")
        self.assertEqual(format_uptime(999 * 86400), ("999d 0h", "0m"))
        self.assertEqual(format_uptime(1000 * 86400), ("2.7y", "0h 0m"))

    def test_header_equalizer_is_one_continuous_interpolation(self) -> None:
        image = Image.new("RGB", (112, 28), "black")
        draw = ImageDraw.Draw(image)
        draw_wide_center_dot_matrix_visualizer(
            draw,
            x_start=1,
            y_base=25,
            m_time=0,
            per_core=(0, 100),
            color=(168, 85, 247),
        )
        heights = []
        for column in (0, 7, 14, 21, 27):
            x = 1 + column * 4
            heights.append(sum(image.getpixel((x, y)) != (0, 0, 0) for y in range(28)))
        self.assertEqual(heights, sorted(heights))
        self.assertLess(heights[0], heights[-1])

    def test_config_paths_are_relative_to_theme(self) -> None:
        config = load_config()
        self.assertEqual(config.assets_dir, THEME_ROOT)
        self.assertEqual(config.fonts_dir, THEME_ROOT / "fonts")

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
                SystemInfo("apple", "Mac mini M4", "macOS 26"),
                threading.Event(),
                max_frames=2,
            )
            output = Path(directory) / "preview.png"
            display.save(output)
            with Image.open(output) as preview:
                self.assertEqual(preview.size, (480, 320))
            self.assertGreater(output.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
