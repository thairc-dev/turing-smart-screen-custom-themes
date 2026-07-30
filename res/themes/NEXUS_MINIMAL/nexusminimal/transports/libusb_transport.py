from __future__ import annotations

import logging

import usb.core
import usb.util

from ..config import DeviceConfig
from .base import DisplayTransport, TransportError

LOG = logging.getLogger(__name__)


class LibusbTransport(DisplayTransport):
    def __init__(self, config: DeviceConfig):
        self.config = config
        self.device = None
        self.interface_number: int | None = None
        self.endpoint_address: int | None = None

    def _is_expected_device(self, device) -> bool:
        if self.config.allow_unverified_device or not self.config.serial_number:
            return True
        try:
            return usb.util.get_string(device, device.iSerialNumber) == self.config.serial_number
        except (usb.core.USBError, ValueError):
            return False

    def open(self) -> None:
        devices = list(usb.core.find(
            find_all=True,
            idVendor=self.config.vendor_id,
            idProduct=self.config.product_id,
        ) or [])
        verified = [device for device in devices if self._is_expected_device(device)]
        if not verified:
            hint = " (serial chưa khớp; đặt allow_unverified_device: true nếu chắc chắn là màn 3.5)"
            raise TransportError("Không tìm thấy TURZX/Turing 3.5 qua libusb" + hint)
        if len(verified) > 1:
            raise TransportError("Có nhiều màn phù hợp; hãy đặt serial_number duy nhất")
        device = verified[0]

        try:
            device.set_configuration()
        except usb.core.USBError as exc:
            if getattr(exc, "errno", None) not in (None, 16):
                raise TransportError(f"Không set được USB configuration: {exc}") from exc

        configuration = device.get_active_configuration()
        selected = None
        if self.config.interface is not None:
            selected = usb.util.find_descriptor(configuration, bInterfaceNumber=self.config.interface)
        else:
            for interface in configuration:
                out_endpoint = usb.util.find_descriptor(
                    interface,
                    custom_match=lambda endpoint:
                        usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_OUT,
                )
                if interface.bInterfaceClass == 10 and out_endpoint is not None:
                    selected = interface
                    break
        if selected is None:
            raise TransportError("Không tìm thấy USB CDC data interface")
        interface_number = int(selected.bInterfaceNumber)

        try:
            if device.is_kernel_driver_active(interface_number):
                device.detach_kernel_driver(interface_number)
        except (NotImplementedError, usb.core.USBError):
            pass
        try:
            usb.util.claim_interface(device, interface_number)
        except usb.core.USBError as exc:
            raise TransportError(
                f"USB interface {interface_number} đang bị hệ điều hành giữ: {exc}"
            ) from exc

        if self.config.endpoint is not None:
            endpoint_address = self.config.endpoint
        else:
            endpoint = usb.util.find_descriptor(
                selected,
                custom_match=lambda candidate:
                    usb.util.endpoint_direction(candidate.bEndpointAddress) == usb.util.ENDPOINT_OUT,
            )
            if endpoint is None:
                usb.util.release_interface(device, interface_number)
                raise TransportError("Không tìm thấy USB OUT endpoint")
            endpoint_address = int(endpoint.bEndpointAddress)
        try:
            device.clear_halt(endpoint_address)
        except usb.core.USBError:
            pass
        self.device = device
        self.interface_number = interface_number
        self.endpoint_address = endpoint_address
        LOG.info("Connected using libusb interface %d endpoint %#04x", interface_number, endpoint_address)

    def write(self, data: bytes | bytearray | memoryview, timeout_ms: int = 1000) -> None:
        if self.device is None or self.endpoint_address is None:
            raise TransportError("Libusb transport is not open")
        try:
            written = self.device.write(self.endpoint_address, data, timeout=timeout_ms)
        except usb.core.USBError as exc:
            raise TransportError(f"USB write failed: {exc}") from exc
        if written != len(data):
            raise TransportError(f"Short USB write: {written}/{len(data)} bytes")

    def close(self) -> None:
        if self.device is not None:
            if self.interface_number is not None:
                try:
                    usb.util.release_interface(self.device, self.interface_number)
                except usb.core.USBError:
                    pass
            usb.util.dispose_resources(self.device)
        self.device = None
        self.interface_number = None
        self.endpoint_address = None
