from __future__ import annotations

from collections import deque
import logging
import time

from PIL import Image, ImageDraw, ImageFont

from .config import AppConfig
from .metrics import MetricsCollector, MetricsSnapshot, SystemInfo, display_model_name
from .protocol import (
    CLEAR,
    DISPLAY_BITMAP,
    SCREEN_OFF,
    SCREEN_ON,
    SET_BRIGHTNESS,
    build_command,
    image_to_rgb565le,
    orientation_command,
)
from .transports.base import DisplayTransport


LOG = logging.getLogger(__name__)
W, H = 480, 320

BG = (5, 7, 9)
PANEL = (9, 12, 15)
WHITE = (232, 235, 235)
MUTED = (153, 160, 171)
DIM = (73, 80, 90)
BORDER = (35, 41, 48)
GRID = (25, 31, 36)
BAR_OFF = (24, 29, 35)
GREEN = (116, 213, 91)
PURPLE = (158, 76, 235)
BLUE = (79, 128, 235)
ORANGE = (247, 126, 39)
YELLOW = (234, 195, 60)

PIXEL_DIGITS = {
    "0": ("11111", "10001", "10011", "10101", "11001", "10001", "11111"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("11110", "00001", "00001", "11110", "10000", "10000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("10010", "10010", "10010", "11111", "00010", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01111", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "11110"),
    ":": ("0", "1", "1", "0", "1", "1", "0"),
}


def _font(path, size):
    return ImageFont.truetype(str(path), size)


def _text_right(draw, x, y, text, font, fill=WHITE):
    draw.text((x - draw.textlength(text, font=font), y), text, font=font, fill=fill)


def _text_center(draw, x, y, text, font, fill=WHITE):
    draw.text((x - draw.textlength(text, font=font) / 2, y), text, font=font, fill=fill)


def draw_pixel_clock(draw, x, y, text, scale=7, fill=WHITE):
    cursor = x
    for character in text:
        glyph = PIXEL_DIGITS.get(character)
        if glyph is None:
            continue
        width = len(glyph[0])
        for row, line in enumerate(glyph):
            for column, bit in enumerate(line):
                if bit == "1":
                    x0 = cursor + column * scale
                    y0 = y + row * scale
                    draw.rectangle(
                        [x0, y0, x0 + scale - 1, y0 + scale - 1],
                        fill=fill,
                    )
        cursor += (width + 1) * scale
    return cursor


def draw_computer(draw, x, y, color=WHITE):
    draw.rounded_rectangle([x, y, x + 25, y + 17], radius=1, outline=color, width=2)
    draw.line([(x + 12, y + 18), (x + 12, y + 22)], fill=color, width=2)
    draw.line([(x + 7, y + 22), (x + 18, y + 22)], fill=color, width=2)


def draw_wifi(draw, x, y, active=True):
    color = WHITE if active else DIM
    draw.arc([x, y, x + 26, y + 22], 215, 325, fill=color, width=2)
    draw.arc([x + 5, y + 5, x + 21, y + 19], 215, 325, fill=color, width=2)
    draw.ellipse([x + 11, y + 16, x + 15, y + 20], fill=color)


def draw_terminal_mark(draw, x, y, color=GREEN):
    draw.line([(x, y), (x + 7, y + 7), (x, y + 14)], fill=color, width=2)
    draw.line([(x + 10, y + 14), (x + 20, y + 14)], fill=color, width=2)


def draw_arrow(draw, x, y, direction, color=WHITE):
    if direction == "up":
        draw.line([(x + 6, y + 17), (x + 6, y)], fill=color, width=2)
        draw.line([(x + 1, y + 5), (x + 6, y), (x + 11, y + 5)], fill=color, width=2)
    else:
        draw.line([(x + 6, y), (x + 6, y + 17)], fill=color, width=2)
        draw.line([(x + 1, y + 12), (x + 6, y + 17), (x + 11, y + 12)], fill=color, width=2)


def draw_chip(draw, x, y, color=WHITE):
    draw.rectangle([x + 5, y + 5, x + 23, y + 23], outline=color, width=2)
    draw.rectangle([x + 10, y + 10, x + 18, y + 18], outline=color, width=1)
    for offset in (8, 14, 20):
        draw.line([(x + offset, y + 1), (x + offset, y + 5)], fill=color)
        draw.line([(x + offset, y + 23), (x + offset, y + 27)], fill=color)
        draw.line([(x + 1, y + offset), (x + 5, y + offset)], fill=color)
        draw.line([(x + 23, y + offset), (x + 27, y + offset)], fill=color)


def draw_ram(draw, x, y, color=WHITE):
    draw.rectangle([x + 1, y + 6, x + 29, y + 19], outline=color, width=2)
    for offset in (6, 13, 20):
        draw.rectangle([x + offset, y + 9, x + offset + 4, y + 15], outline=color)
    for offset in (5, 12, 19, 26):
        draw.line([(x + offset, y + 19), (x + offset, y + 23)], fill=color)


def draw_ssd(draw, x, y, color=WHITE):
    draw.polygon([(x + 5, y + 3), (x + 25, y + 3), (x + 29, y + 22), (x + 1, y + 22)], outline=color)
    draw.line([(x + 2, y + 17), (x + 28, y + 17)], fill=color)
    draw.ellipse([x + 22, y + 19, x + 24, y + 21], fill=color)


def draw_fan(draw, x, y, color=WHITE):
    cx, cy = x + 14, y + 14
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], outline=color)
    draw.ellipse([cx - 4, cy - 13, cx + 4, cy - 4], outline=color, width=2)
    draw.ellipse([cx + 4, cy - 4, cx + 13, cy + 4], outline=color, width=2)
    draw.ellipse([cx - 4, cy + 4, cx + 4, cy + 13], outline=color, width=2)
    draw.ellipse([cx - 13, cy - 4, cx - 4, cy + 4], outline=color, width=2)


def draw_thermometer(draw, x, y, color=WHITE):
    draw.rounded_rectangle([x + 8, y + 1, x + 15, y + 20], radius=4, outline=color, width=2)
    draw.ellipse([x + 5, y + 17, x + 18, y + 30], outline=color, width=2)
    draw.line([(x + 11, y + 8), (x + 11, y + 23)], fill=color, width=2)


def draw_segment_bar(draw, box, percent, segments=13):
    x0, y0, x1, y1 = box
    percent = max(0.0, min(100.0, percent))
    gap = 2
    width = (x1 - x0 - gap * (segments - 1)) / segments
    lit = round(percent / 100 * segments)
    for index in range(segments):
        left = round(x0 + index * (width + gap))
        right = round(left + width)
        draw.rectangle([left, y0, right, y1], fill=WHITE if index < lit else BAR_OFF)


def draw_progress_bar(draw, box, percent, color):
    x0, y0, x1, y1 = box
    percent = max(0.0, min(100.0, float(percent)))
    draw.rounded_rectangle(box, radius=max(1, (y1 - y0) // 2), fill=BAR_OFF)
    width = round((x1 - x0) * percent / 100)
    if width > 0:
        draw.rounded_rectangle(
            [x0, y0, max(x0 + 1, x0 + width), y1],
            radius=max(1, (y1 - y0) // 2),
            fill=color,
        )


def draw_line_graph(draw, box, values, minimum=0.0, maximum=100.0, grid=False, color=WHITE):
    x0, y0, x1, y1 = box
    if grid:
        for ratio in (0.0, 0.5, 1.0):
            y = round(y1 - ratio * (y1 - y0))
            for x in range(x0, x1 + 1, 4):
                draw.point((x, y), fill=GRID)
    if not values:
        return
    values = list(values)
    if len(values) == 1:
        values *= 2
    points = []
    for index, value in enumerate(values):
        ratio = (max(minimum, min(maximum, value)) - minimum) / max(0.001, maximum - minimum)
        x = x0 + index * (x1 - x0) / (len(values) - 1)
        y = y1 - ratio * (y1 - y0)
        points.append((round(x), round(y)))
    if len(points) >= 2:
        fill_points = points + [(x1, y1), (x0, y1)]
        draw.polygon(fill_points, fill=(17, 21, 22))
        draw.line(points, fill=color, width=1)


def format_rate(rate):
    rate = max(0.0, float(rate))
    if rate < 100:
        return f"{rate:.1f}"
    if rate < 1000:
        return f"{rate:.0f}"
    return f"{min(99.9, rate / 1000):.1f}K"


def format_uptime(seconds):
    seconds = max(0, int(seconds))
    days = seconds // 86400
    hours = seconds % 86400 // 3600
    minutes = seconds % 3600 // 60
    if days >= 1000:
        return f"{days / 365.25:.1f}y {hours}h"
    return f"{days}d {hours}h {minutes}m"


def format_fan(rpm):
    if rpm is None:
        return "N/A", "NO SENSOR"
    return f"{rpm} RPM", "SILENT" if rpm == 0 else "ACTIVE"


def format_temperature(snapshot):
    temperature = snapshot.cpu_temp_c
    if temperature is None:
        temperature = snapshot.gpu_temp_c
    return "N/A" if temperature is None else f"{temperature:.0f}°C"


def render_frame(
    config: AppConfig,
    snapshot: MetricsSnapshot,
    system_info: SystemInfo,
    cpu_history,
):
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    regular = config.fonts_dir / "RobotoMono-Regular.ttf"
    bold = config.fonts_dir / "RobotoMono-Bold.ttf"
    f8 = _font(regular, 8)
    f9 = _font(regular, 9)
    f10 = _font(regular, 10)
    f11 = _font(regular, 11)
    f12 = _font(regular, 12)
    f13 = _font(bold, 13)
    f16 = _font(bold, 16)
    f20 = _font(bold, 20)

    # Terminal identity and real default-route throughput.
    draw_terminal_mark(draw, 24, 17)
    draw.text((58, 12), display_model_name(system_info, 24), font=f13, fill=WHITE)
    draw.text((58, 29), system_info.os_version, font=f9, fill=MUTED)
    draw_wifi(draw, 437, 15, bool(snapshot.network_interface))
    draw.text((268, 20), "NET", font=f9, fill=MUTED)
    draw.line([(298, 14), (298, 39)], fill=BORDER)
    draw_arrow(draw, 308, 15, "up", GREEN)
    draw.text((325, 11), format_rate(snapshot.net_up_mb_s), font=f12, fill=GREEN)
    draw.text((325, 28), "MB/s", font=f8, fill=MUTED)
    draw_arrow(draw, 375, 15, "down", BLUE)
    draw.text((392, 11), format_rate(snapshot.net_down_mb_s), font=f12, fill=BLUE)
    draw.text((392, 28), "MB/s", font=f8, fill=MUTED)

    # Large clock, uptime and the same real CPU history used by the CPU card.
    draw_pixel_clock(draw, 25, 56, time.strftime("%H:%M"), scale=7)
    draw.text((27, 111), time.strftime("%a %d %b %Y").upper(), font=f13, fill=WHITE)
    draw.line([(26, 136), (238, 136)], fill=BORDER)
    draw.text((27, 149), "UPTIME", font=f9, fill=GREEN)
    draw.text((27, 166), format_uptime(snapshot.uptime_seconds), font=f12, fill=WHITE)
    draw.line([(130, 149), (130, 211)], fill=BORDER)
    draw_line_graph(draw, (142, 153, 238, 192), cpu_history, grid=True, color=GREEN)
    _text_right(draw, 238, 196, "60 SEC", f9, MUTED)

    # Right cards.
    cpu_box = (248, 54, 468, 108)
    ram_box = (248, 114, 468, 164)
    ssd_box = (248, 170, 468, 220)
    for box in (cpu_box, ram_box, ssd_box):
        draw.rounded_rectangle(box, radius=6, fill=PANEL, outline=BORDER)

    draw_chip(draw, 258, 65, GREEN)
    draw.text((296, 63), "CPU", font=f11, fill=WHITE)
    _text_right(draw, 455, 60, f"{snapshot.cpu_percent:.0f}%", f20, GREEN)
    draw_line_graph(draw, (296, 82, 390, 99), cpu_history, color=GREEN)
    frequency = snapshot.cpu_frequency_ghz
    frequency_text = "N/A" if frequency is None else f"{frequency:.1f} GHz"
    _text_right(draw, 455, 84, frequency_text, f9, MUTED)

    draw_ram(draw, 258, 120, PURPLE)
    draw.text((296, 121), "RAM", font=f11, fill=WHITE)
    _text_right(draw, 455, 118, f"{snapshot.ram_percent:.0f}%", f20, PURPLE)
    draw_progress_bar(draw, (258, 143, 455, 149), snapshot.ram_percent, PURPLE)
    draw.text(
        (258, 151),
        f"{snapshot.ram_used_gb:.1f} / {snapshot.ram_total_gb:.0f} GiB",
        font=f8,
        fill=MUTED,
    )

    draw_ssd(draw, 258, 175, BLUE)
    draw.text((296, 177), "SSD", font=f11, fill=WHITE)
    _text_right(draw, 455, 174, f"{snapshot.disk_percent:.0f}%", f20, BLUE)
    draw_progress_bar(draw, (258, 199, 455, 205), snapshot.disk_percent, BLUE)
    draw.text(
        (258, 207),
        f"{snapshot.disk_used_gb:.0f} / {snapshot.disk_total_gb:.0f} GB",
        font=f8,
        fill=MUTED,
    )

    # Four independent real-value utility cards.
    utility_boxes = (
        (14, 229, 124, 314),
        (130, 229, 240, 314),
        (246, 229, 354, 314),
        (360, 229, 468, 314),
    )
    for box in utility_boxes:
        draw.rounded_rectangle(box, radius=6, fill=PANEL, outline=BORDER)
    fan_value, fan_status = format_fan(snapshot.fan_rpm)
    draw_fan(draw, 24, 249, MUTED)
    draw.text((59, 241), "FAN", font=f9, fill=MUTED)
    draw.text((59, 256), fan_value, font=f11, fill=WHITE)
    draw.text((59, 274), fan_status, font=f8, fill=MUTED)

    draw_thermometer(draw, 141, 249, MUTED)
    draw.text((176, 241), "TEMP", font=f9, fill=MUTED)
    temperature = format_temperature(snapshot)
    draw.text((176, 256), temperature, font=f13, fill=ORANGE if temperature != "N/A" else MUTED)

    draw.line([(258, 260), (268, 260), (273, 252), (278, 268), (283, 256), (290, 260)], fill=MUTED)
    draw.text((291, 241), "LOAD", font=f9, fill=MUTED)
    load_text = "N/A" if snapshot.load_average_1m is None else f"{snapshot.load_average_1m:.2f}"
    draw.text((291, 256), load_text, font=f16, fill=YELLOW)
    draw.text((291, 277), "1m avg", font=f8, fill=MUTED)

    draw.rectangle([371, 249, 392, 266], outline=MUTED)
    draw.text((375, 251), ">_", font=f9, fill=BLUE)
    draw.text((401, 241), "PROCS", font=f9, fill=MUTED)
    draw.text((401, 256), str(snapshot.process_count), font=f16, fill=BLUE)
    draw.text((401, 277), "TOTAL", font=f8, fill=MUTED)
    return image


def _send_frame(transport, image, chunk_size):
    transport.write(build_command(DISPLAY_BITMAP, 0, 0, W - 1, H - 1), timeout_ms=1000)
    payload = image_to_rgb565le(image)
    for offset in range(0, len(payload), chunk_size):
        transport.write(payload[offset:offset + chunk_size], timeout_ms=2000)
        time.sleep(0.001)
    # Rev-A requires a short gap between bitmap payload and the next command.
    time.sleep(0.025)


def cleanse_display(transport, chunk_size):
    """Clear the Rev-A controller's native portrait GRAM, then restore landscape."""
    black = Image.new("RGB", (W, H), (0, 0, 0))
    transport.write(build_command(SCREEN_OFF))
    time.sleep(0.05)
    transport.write(orientation_command(320, 480, orientation=0))
    time.sleep(0.05)
    transport.write(build_command(CLEAR))
    time.sleep(0.50)
    transport.write(orientation_command(W, H, orientation=3))
    time.sleep(0.10)
    _send_frame(transport, black, chunk_size)


def render_session(
    config: AppConfig,
    transport: DisplayTransport,
    metrics: MetricsCollector,
    system_info: SystemInfo,
    stop_event,
    max_frames: int | None = None,
):
    if config.display.clean_on_startup:
        LOG.info("Clearing native portrait GRAM before landscape render")
        cleanse_display(
            transport,
            config.device.chunk_size,
        )
    transport.write(build_command(SCREEN_ON))
    brightness_value = int(255 - config.display.brightness * 2.55)
    transport.write(build_command(SET_BRIGHTNESS, brightness_value, 0, 0, 0))
    transport.write(orientation_command(W, H))
    time.sleep(0.2)

    initial = metrics.snapshot()
    history = deque([initial.cpu_percent] * 60, maxlen=60)
    history_initialized = initial.cpu_percent > 0
    frames = 0
    LOG.info("NEXUS MINIMAL renderer started (%s, %s)", system_info.kind, system_info.model)

    while not stop_event.is_set():
        if max_frames is not None and frames >= max_frames:
            break
        snapshot = metrics.snapshot()
        if not history_initialized and snapshot.cpu_percent > 0:
            history = deque([snapshot.cpu_percent] * 60, maxlen=60)
            history_initialized = True
        else:
            history.append(snapshot.cpu_percent)
        frame = render_frame(config, snapshot, system_info, history)
        _send_frame(transport, frame, config.device.chunk_size)
        frames += 1
        stop_event.wait(config.display.stats_interval)
