from __future__ import annotations

import argparse
from logging.handlers import RotatingFileHandler
import logging
import platform
import signal
import sys
import threading
import time

from .config import AppConfig, load_config
from .metrics import MetricsCollector, detect_system_info
from .renderer import render_session
from .transports.base import DisplayTransport, TransportError
from .transports.preview_transport import PreviewTransport
from .weather import WeatherCollector

LOG = logging.getLogger(__name__)


def configure_logging(config: AppConfig) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if config.log_file:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                config.log_file,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def transport_name(config: AppConfig) -> str:
    if config.device.transport != "auto":
        return config.device.transport
    return "libusb" if platform.system() == "Darwin" else "serial"


def create_transport(config: AppConfig) -> DisplayTransport:
    name = transport_name(config)
    if name == "libusb":
        from .transports.libusb_transport import LibusbTransport
        return LibusbTransport(config.device)
    if name == "serial":
        from .transports.serial_transport import SerialTransport
        return SerialTransport(config.device)
    if name == "preview":
        return PreviewTransport(config.display.width, config.display.height)
    raise ValueError(f"Unsupported transport: {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NEXUS 26 portable TURZX 3.5 theme")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--preview", metavar="PNG", help="Render a local preview without a display")
    parser.add_argument("--once", action="store_true", help="Exit instead of reconnecting")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    configure_logging(config)

    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    metrics = MetricsCollector(
        interval=config.metrics.interval,
        network_interface=config.metrics.network_interface,
    )
    weather = WeatherCollector(config.weather)
    metrics.start()
    weather.start()
    system_info = detect_system_info()

    if args.preview:
        transport = PreviewTransport(config.display.width, config.display.height)
        transport.open()
        try:
            render_session(
                config, transport, metrics, weather, system_info, stop_event, max_frames=25
            )
            transport.save(args.preview)
            LOG.info("Preview saved to %s", args.preview)
            return 0
        finally:
            transport.close()
            weather.stop()
            metrics.stop()

    try:
        while not stop_event.is_set():
            transport = create_transport(config)
            try:
                with transport:
                    render_session(config, transport, metrics, weather, system_info, stop_event)
            except (OSError, TransportError) as exc:
                LOG.warning("Display disconnected or unavailable: %s", exc)
            if args.once:
                return 1
            stop_event.wait(config.display.reconnect_interval)
    finally:
        weather.stop()
        metrics.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
