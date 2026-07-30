from __future__ import annotations

import argparse
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import platform
import sys
import threading

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
    parser = argparse.ArgumentParser(description="NOVA 01 display renderer")
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        help="Save a single frame preview to the specified path and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    configure_logging(config)

    metrics = MetricsCollector(config.display.stats_interval)
    metrics.start()

    weather = WeatherCollector(config.weather)
    weather.start()

    system_info = detect_system_info()
    stop_event = threading.Event()

    try:
        if args.preview:
            transport = PreviewTransport(config.display.width, config.display.height)
            render_session(
                config,
                transport,
                metrics,
                weather,
                system_info,
                stop_event,
                max_frames=1,
            )
            args.preview.parent.mkdir(parents=True, exist_ok=True)
            transport.save(args.preview)
            LOG.info("Preview saved to %s", args.preview)
            return

        transport = create_transport(config)
        with transport:
            render_session(
                config,
                transport,
                metrics,
                weather,
                system_info,
                stop_event,
            )
    except (KeyboardInterrupt, TransportError) as exc:
        LOG.info("Exiting NOVA 01 session: %s", exc)
    finally:
        stop_event.set()
        weather.stop()
        metrics.stop()


if __name__ == "__main__":
    main()
