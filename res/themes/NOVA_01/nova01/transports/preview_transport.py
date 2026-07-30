from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..protocol import DISPLAY_BITMAP
from .base import DisplayTransport


class PreviewTransport(DisplayTransport):
    """In-memory display used for previews and CI tests."""

    def __init__(self, width: int = 480, height: int = 320):
        self.writes: list[bytes] = []
        self.image = Image.new("RGB", (width, height), (0, 0, 0))
        self._region: tuple[int, int, int, int] | None = None
        self._expected = 0
        self._buffer = bytearray()

    def open(self) -> None:
        return None

    def write(self, data: bytes | bytearray | memoryview, timeout_ms: int = 1000) -> None:
        del timeout_ms
        payload = bytes(data)
        self.writes.append(payload)
        if len(payload) == 6 and payload[5] == DISPLAY_BITMAP:
            x0 = payload[0] << 2 | payload[1] >> 6
            y0 = (payload[1] & 0x3F) << 4 | payload[2] >> 4
            x1 = (payload[2] & 0x0F) << 6 | payload[3] >> 2
            y1 = (payload[3] & 0x03) << 8 | payload[4]
            self._region = (x0, y0, x1, y1)
            self._expected = (x1 - x0 + 1) * (y1 - y0 + 1) * 2
            self._buffer.clear()
        elif self._region is not None:
            self._buffer.extend(payload)
            if len(self._buffer) >= self._expected:
                self._commit_region()

    def _commit_region(self) -> None:
        if self._region is None:
            return
        x0, y0, x1, y1 = self._region
        rgb = bytearray(((x1 - x0 + 1) * (y1 - y0 + 1)) * 3)
        output_index = 0
        for index in range(0, self._expected, 2):
            value = self._buffer[index] | self._buffer[index + 1] << 8
            rgb[output_index] = ((value >> 11) & 0x1F) * 255 // 31
            rgb[output_index + 1] = ((value >> 5) & 0x3F) * 255 // 63
            rgb[output_index + 2] = (value & 0x1F) * 255 // 31
            output_index += 3
        region = Image.frombytes("RGB", (x1 - x0 + 1, y1 - y0 + 1), bytes(rgb))
        self.image.paste(region, (x0, y0))
        self._region = None
        self._expected = 0
        self._buffer.clear()

    def save(self, path: str | Path) -> None:
        self.image.save(path)

    def close(self) -> None:
        return None
