from __future__ import annotations

import platform

from .base import DisplayTransport, TransportError
from .preview_transport import PreviewTransport
from .serial_transport import SerialTransport
from .libusb_transport import LibusbTransport


def connect_transport(config) -> DisplayTransport:
    transport_type = getattr(config, "transport", "auto")
    if transport_type == "auto":
        transport_type = "libusb" if platform.system() == "Darwin" else "serial"

    if transport_type == "libusb":
        t = LibusbTransport(config)
        t.open()
        return t
    if transport_type == "serial":
        t = SerialTransport(config)
        t.open()
        return t
    if transport_type == "preview":
        t = PreviewTransport()
        t.open()
        return t
    raise ValueError(f"Unsupported transport: {transport_type}")


__all__ = [
    "DisplayTransport",
    "TransportError",
    "PreviewTransport",
    "SerialTransport",
    "LibusbTransport",
    "connect_transport",
]
