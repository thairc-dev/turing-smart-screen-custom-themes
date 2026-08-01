from __future__ import annotations

import logging
import time

import serial
from serial.tools.list_ports import comports

from ..config import DeviceConfig
from .base import DisplayTransport, TransportError

LOG = logging.getLogger(__name__)


class SerialTransport(DisplayTransport):
    def __init__(self, config: DeviceConfig):
        self.config = config
        self.connection: serial.Serial | None = None

    def _detect_port(self) -> str:
        if self.config.port.upper() != "AUTO":
            return self.config.port
        candidates = []
        for port in comports():
            if "usbserial-2120" in port.device:
                continue
            if self.config.serial_number and port.serial_number == self.config.serial_number:
                return port.device
            if port.vid == self.config.vendor_id and port.pid == self.config.product_id:
                candidates.append(port)
        if not candidates:
            raise TransportError("Không tìm thấy TURZX/Turing 3.5 trên cổng serial")
        if len(candidates) > 1 and not self.config.allow_unverified_device:
            names = ", ".join(port.device for port in candidates)
            raise TransportError(f"Có nhiều thiết bị VID/PID phù hợp ({names}); hãy đặt device.port")
        return candidates[0].device

    def open(self) -> None:
        port = self._detect_port()
        try:
            self.connection = serial.Serial(port, 115200, timeout=1, write_timeout=2, rtscts=False)
            self.connection.reset_input_buffer()
            self.connection.reset_output_buffer()
            LOG.info("Connected using serial transport on %s", port)
        except (OSError, serial.SerialException) as exc:
            raise TransportError(f"Không mở được cổng {port}: {exc}") from exc

    def write(self, data: bytes | bytearray | memoryview, timeout_ms: int = 1000) -> None:
        if self.connection is None:
            raise TransportError("Serial transport is not open")
        self.connection.write_timeout = max(0.1, timeout_ms / 1000)
        try:
            written = self.connection.write(data)
            self.connection.flush()
        except (OSError, serial.SerialException) as exc:
            raise TransportError(f"Serial write failed: {exc}") from exc
        if written != len(data):
            raise TransportError(f"Short serial write: {written}/{len(data)} bytes")
        if len(data) > 4096:
            time.sleep(0.001)

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None
