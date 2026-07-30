from __future__ import annotations

import plistlib
import time
import unittest
from unittest.mock import patch

import psutil

from nexus26.metrics import MetricsCollector, classify_health, network_rate_mb_s
from nexus26.weather import compact_condition


class MetricsAuditTests(unittest.TestCase):
    def test_network_rate_uses_decimal_megabytes(self) -> None:
        self.assertEqual(network_rate_mb_s(3_000_000, 1_000_000, 2), 1.0)
        self.assertEqual(network_rate_mb_s(1_000_000, 3_000_000, 2), 0.0)

    def test_apfs_uses_container_not_read_only_snapshot(self) -> None:
        payload = plistlib.dumps({
            "APFSContainerSize": 245_000_000_000,
            "APFSContainerFree": 22_000_000_000,
        })
        with (
            patch("nexus26.metrics.platform.system", return_value="Darwin"),
            patch("nexus26.metrics.subprocess.check_output", return_value=payload),
        ):
            percent, used, total = MetricsCollector._disk_stats()
        self.assertAlmostEqual(percent, 91.02, places=2)
        self.assertEqual(used, 223.0)
        self.assertEqual(total, 245.0)

    def test_health_reason_is_not_generic(self) -> None:
        self.assertEqual(classify_health(20, 30, 50, 91, 50, 45)[0], "DISK")
        self.assertEqual(classify_health(20, 30, 50, 50, 96, 45)[0], "HOT")
        self.assertEqual(classify_health(96, 30, 50, 50, 50, 45)[0], "HEAVY")
        self.assertEqual(classify_health(20, 30, 50, 50, 50, 45)[0], "GOOD")

    def test_weather_descriptions_are_meaningful_and_fit(self) -> None:
        self.assertEqual(compact_condition("Moderate or heavy rain with thunder"), ("THUNDER", "thunder"))
        self.assertEqual(compact_condition("Partly cloudy"), ("PARTLY CLOUDY", "partly_cloudy"))
        self.assertEqual(compact_condition("Light rain shower"), ("RAIN", "rain"))

    def test_uptime_source_matches_boot_time(self) -> None:
        uptime = time.time() - psutil.boot_time()
        self.assertGreaterEqual(uptime, 0)
        self.assertLess(abs(uptime - int(uptime)), 1)


if __name__ == "__main__":
    unittest.main()
