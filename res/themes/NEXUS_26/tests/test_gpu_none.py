"""Test NEXUS_26 renders correctly when sensor data is None (no GPU / no fan / no temp sensor)."""
from __future__ import annotations

import threading
import unittest

from nexus26.config import load_config
from nexus26.metrics import MetricsCollector, MetricsSnapshot, SystemInfo
from nexus26.renderer import draw_concept_smooth_wave_graph, render_session
from nexus26.transports.preview_transport import PreviewTransport
from nexus26.weather import WeatherCollector
from PIL import Image, ImageDraw


class NoSensorMetrics(MetricsCollector):
    """Simulate a machine with NO GPU sensor, NO fan sensor, NO CPU temp."""
    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            cpu_percent=45,
            per_core=(40, 50, 45, 55),
            cpu_temp_c=None,       # No sensor
            gpu_percent=None,      # No GPU sensor
            gpu_temp_c=None,
            ram_percent=60,
            ram_used_gb=9.6,
            ram_total_gb=16,
            disk_percent=70,
            disk_used_gb=170,
            disk_total_gb=245,
            fan_rpm=None,          # No fan sensor
            uptime_seconds=3600,
            warning=False,
            health_status="GOOD",
            health_line1="All systems",
            health_line2="operational",
        )


class TestGpuNoneHandling(unittest.TestCase):

    def test_wave_graph_all_none_does_not_crash(self) -> None:
        """draw_concept_smooth_wave_graph must not crash when history is all None."""
        image = Image.new("RGB", (100, 40), "black")
        draw = ImageDraw.Draw(image)
        # All-None history — should draw a grey baseline and return cleanly
        draw_concept_smooth_wave_graph(draw, [0, 0, 100, 40], [None] * 24)

    def test_wave_graph_partial_none_renders_real_values(self) -> None:
        """draw_concept_smooth_wave_graph should render using only real (non-None) values."""
        image = Image.new("RGB", (100, 40), "black")
        draw = ImageDraw.Draw(image)
        history = [None] * 12 + [50] * 12   # First half unknown, second half 50%
        draw_concept_smooth_wave_graph(draw, [0, 0, 100, 40], history)
        # Should not raise, and some pixels should be non-black
        non_black = sum(image.getpixel((x, y)) != (0, 0, 0) for x in range(100) for y in range(40))
        self.assertGreater(non_black, 0)

    def test_full_render_with_no_sensors_does_not_crash(self) -> None:
        """Full render_session with no GPU/fan/temp sensor must produce a valid 480x320 frame."""
        config = load_config()
        display = PreviewTransport()
        weather = WeatherCollector(config.weather)
        render_session(
            config,
            display,
            NoSensorMetrics(),
            weather,
            SystemInfo("apple", "Mac mini M4", "macOS 26"),
            threading.Event(),
            max_frames=3,
        )
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview.png"
            display.save(output)
            self.assertGreater(output.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
