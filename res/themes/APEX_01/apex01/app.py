from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import threading
import time

from .config import THEME_ROOT, AppConfig
from .metrics import MetricsCollector, detect_system_info
from .protocol import SCREEN_OFF, build_command
from .renderer import render_session
from .transports import PreviewTransport, TransportError, connect_transport
from .weather import WeatherCollector

LOG = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="APEX 01 - Flagship Custom Theme for TURZX 3.5\" USB Smart Display"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to theme.yaml configuration file",
    )
    parser.add_argument(
        "-p",
        "--preview",
        type=Path,
        default=None,
        help="Generate a single PNG preview frame and exit",
    )
    parser.add_argument(
        "--gif",
        type=Path,
        default=None,
        help="Generate an animated GIF preview and exit",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=20,
        help="Number of frames to record when generating animated GIF",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser


def run_preview_session(config: AppConfig, preview_path: Path, gif_path: Path | None = None, max_frames: int = 20) -> None:
    system_info = detect_system_info()
    metrics = MetricsCollector(interval=0.1)
    weather = WeatherCollector(config.weather)
    transport = PreviewTransport(width=config.display.width, height=config.display.height)

    metrics.start()
    weather.start()
    time.sleep(0.3)

    stop_event = threading.Event()
    frames_to_run = max_frames if gif_path else 1

    try:
        render_session(
            config,
            transport,
            metrics,
            weather,
            system_info,
            stop_event,
            max_frames=frames_to_run,
        )
    finally:
        metrics.stop()
        weather.stop()

    if gif_path:
        transport.save_gif(gif_path)
        LOG.info("Animated GIF saved to %s", gif_path)
    else:
        transport.save(preview_path)
        LOG.info("Preview saved to %s", preview_path)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    config_path = args.config
    if config_path is None:
        default_theme_yaml = THEME_ROOT / "theme.yaml"
        if default_theme_yaml.exists():
            config_path = default_theme_yaml

    config = AppConfig.load(config_path)

    if args.preview or args.gif:
        preview_out = args.preview or THEME_ROOT / "preview.png"
        run_preview_session(config, preview_out, gif_path=args.gif, max_frames=args.frames)
        return 0

    system_info = detect_system_info()
    metrics = MetricsCollector(interval=config.display.stats_interval)
    weather = WeatherCollector(config.weather)

    metrics.start()
    weather.start()

    stop_event = threading.Event()

    try:
        while not stop_event.is_set():
            transport = None
            try:
                LOG.info("Connecting to USB display device...")
                transport = connect_transport(config.device)
                LOG.info("Connected successfully (%s)", transport.__class__.__name__)

                render_session(
                    config,
                    transport,
                    metrics,
                    weather,
                    system_info,
                    stop_event,
                )
            except TransportError as exc:
                LOG.warning("Transport error: %s. Retrying in %.1fs...", exc, config.display.reconnect_interval)
                stop_event.wait(config.display.reconnect_interval)
            except Exception:
                LOG.exception("Unexpected error in main render loop. Retrying in %.1fs...", config.display.reconnect_interval)
                stop_event.wait(config.display.reconnect_interval)
            finally:
                if transport:
                    try:
                        transport.write(build_command(SCREEN_OFF))
                    except Exception:
                        pass
                    transport.close()
    except KeyboardInterrupt:
        LOG.info("Shutdown requested via KeyboardInterrupt")
    finally:
        stop_event.set()
        metrics.stop()
        weather.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
