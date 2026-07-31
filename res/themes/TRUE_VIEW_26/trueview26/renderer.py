from __future__ import annotations

from collections import deque
import logging
import math
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
from .weather import WeatherCollector


LOG = logging.getLogger(__name__)
W, H = 480, 320

BG = (3, 5, 6)
PANEL = (5, 8, 9)
WHITE = (232, 235, 235)
MUTED = (156, 163, 164)
DIM = (74, 81, 82)
BORDER = (43, 49, 50)
GRID = (27, 32, 33)
BAR_OFF = (31, 36, 37)

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


def draw_arrow(draw, x, y, direction):
    if direction == "up":
        draw.line([(x + 6, y + 17), (x + 6, y)], fill=WHITE, width=2)
        draw.line([(x + 1, y + 5), (x + 6, y), (x + 11, y + 5)], fill=WHITE, width=2)
    else:
        draw.line([(x + 6, y), (x + 6, y + 17)], fill=WHITE, width=2)
        draw.line([(x + 1, y + 12), (x + 6, y + 17), (x + 11, y + 12)], fill=WHITE, width=2)


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


def draw_load(draw, x, y, color=WHITE):
    points = [
        (x + 1, y + 15),
        (x + 6, y + 15),
        (x + 9, y + 8),
        (x + 13, y + 20),
        (x + 17, y + 4),
        (x + 21, y + 15),
        (x + 28, y + 15),
    ]
    draw.line(points, fill=color, width=2)
    draw.line([(x + 1, y + 23), (x + 28, y + 23)], fill=DIM)


def draw_terminal(draw, x, y, color=WHITE):
    draw.rounded_rectangle([x + 1, y + 4, x + 28, y + 24], radius=2, outline=color, width=2)
    draw.line([(x + 7, y + 10), (x + 11, y + 14), (x + 7, y + 18)], fill=color, width=2)
    draw.line([(x + 14, y + 18), (x + 21, y + 18)], fill=color, width=2)


def draw_weather(draw, x, y, condition="partly_cloudy"):
    sun = (250, 204, 21)
    cloud = (148, 163, 184)
    rain = (96, 165, 250)

    if condition == "fog":
        for offset in (8, 14, 20):
            draw.line([(x + 2, y + offset), (x + 30, y + offset)], fill=cloud, width=2)
        return

    if condition in {"clear", "partly_cloudy", "unknown"}:
        sun_cx = x + (15 if condition == "clear" else 23)
        sun_cy = y + (14 if condition == "clear" else 8)
        draw.ellipse(
            [sun_cx - 6, sun_cy - 6, sun_cx + 6, sun_cy + 6],
            outline=sun,
            width=2,
        )
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            draw.line(
                [
                    (
                        round(sun_cx + math.cos(radians) * 8),
                        round(sun_cy + math.sin(radians) * 8),
                    ),
                    (
                        round(sun_cx + math.cos(radians) * 11),
                        round(sun_cy + math.sin(radians) * 11),
                    ),
                ],
                fill=sun,
                width=1,
            )
        if condition == "clear":
            return

    draw.ellipse([x + 1, y + 15, x + 12, y + 26], fill=BG)
    draw.ellipse([x + 7, y + 10, x + 24, y + 27], fill=BG)
    draw.ellipse([x + 19, y + 15, x + 32, y + 27], fill=BG)
    draw.rectangle([x + 6, y + 19, x + 27, y + 27], fill=BG)
    draw.arc([x + 1, y + 15, x + 12, y + 26], 90, 270, fill=cloud, width=2)
    draw.arc([x + 7, y + 10, x + 24, y + 27], 180, 326, fill=cloud, width=2)
    draw.arc([x + 19, y + 15, x + 32, y + 27], 270, 450, fill=cloud, width=2)
    draw.line([(x + 6, y + 27), (x + 27, y + 27)], fill=cloud, width=2)

    if condition == "rain":
        for offset in (9, 17, 25):
            draw.line([(x + offset, y + 29), (x + offset - 2, y + 32)], fill=rain)
    elif condition == "snow":
        for offset in (9, 17, 25):
            draw.point((x + offset, y + 31), fill=rain)
    elif condition == "thunder":
        draw.line(
            [(x + 18, y + 27), (x + 14, y + 33), (x + 18, y + 32), (x + 15, y + 36)],
            fill=sun,
            width=2,
        )


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


def draw_line_graph(draw, box, values, minimum=0.0, maximum=100.0, grid=False):
    x0, y0, x1, y1 = box
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
        if grid:
            for ratio in (0.0, 0.5, 1.0):
                y = round(y1 - ratio * (y1 - y0))
                for x in range(x0, x1 + 1, 4):
                    draw.point((x, y), fill=GRID)
        draw.line(points, fill=WHITE, width=1)


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
    weather_snapshot,
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
    f14 = _font(bold, 14)
    f15 = _font(bold, 15)
    f16 = _font(bold, 16)
    f20 = _font(bold, 20)
    f24 = _font(bold, 24)

    # System identity and current route.
    draw_computer(draw, 24, 15)
    draw.text((58, 12), display_model_name(system_info, 24), font=f13, fill=WHITE)
    draw.text((58, 29), system_info.os_version, font=f9, fill=MUTED)
    draw_wifi(draw, 437, 15, bool(snapshot.network_interface))

    draw_arrow(draw, 258, 15, "up")
    draw.text((275, 11), format_rate(snapshot.net_up_mb_s), font=f12, fill=WHITE)
    draw.text((275, 28), "MB/s", font=f8, fill=MUTED)
    draw_arrow(draw, 337, 15, "down")
    draw.text((354, 11), format_rate(snapshot.net_down_mb_s), font=f12, fill=WHITE)
    draw.text((354, 28), "MB/s", font=f8, fill=MUTED)

    # Left information column.
    draw_pixel_clock(draw, 25, 56, time.strftime("%H:%M"), scale=7)
    draw.text((27, 111), time.strftime("%a %d %b %Y").upper(), font=f13, fill=WHITE)
    draw.line([(26, 136), (238, 136)], fill=BORDER)
    draw.text((27, 147), "UPTIME", font=f9, fill=MUTED)
    _text_right(draw, 238, 145, format_uptime(snapshot.uptime_seconds), f11)
    draw.line([(26, 167), (238, 167)], fill=BORDER)
    draw.text((27, 174), "WEATHER", font=f9, fill=MUTED)
    location_label = (weather_snapshot.location or "LIVE").upper()
    if len(location_label) > 12:
        location_label = location_label[:11] + "…"
    _text_right(draw, 238, 174, location_label, font=f8, fill=MUTED)
    draw_weather(draw, 28, 190, weather_snapshot.condition)
    draw.text((70, 187), weather_snapshot.temperature, font=f20, fill=WHITE)
    draw.text((70, 211), weather_snapshot.description, font=f8, fill=MUTED)

    # Vertical divider and Right-side weather stats (eliminates empty space x=162..238)
    draw.line([(162, 178), (162, 218)], fill=BORDER)
    draw.text((170, 186), f"H {weather_snapshot.high_c}", font=f8, fill=(255, 120, 80))
    draw.text((205, 186), f"L {weather_snapshot.low_c}", font=f8, fill=(96, 165, 250))
    draw.text((170, 204), f"HUM {weather_snapshot.humidity}", font=f8, fill=MUTED)

    # Right cards.
    cpu_box = (248, 54, 468, 119)
    ram_box = (248, 125, 468, 170)
    ssd_box = (248, 176, 468, 221)
    for box in (cpu_box, ram_box, ssd_box):
        draw.rounded_rectangle(box, radius=6, fill=PANEL, outline=BORDER)

    draw.text((260, 62), "CPU", font=f12, fill=WHITE)
    _text_right(draw, 455, 56, f"{snapshot.cpu_percent:.0f}%", f24)
    draw.text((260, 77), "100", font=f8, fill=MUTED)
    draw.text((260, 90), "50", font=f8, fill=MUTED)
    draw.text((260, 103), "0", font=f8, fill=MUTED)
    draw_line_graph(draw, (278, 80, 397, 105), cpu_history, grid=True)
    frequency = snapshot.cpu_frequency_ghz
    frequency_text = "N/A" if frequency is None else f"{frequency:.1f} GHz"
    _text_right(draw, 455, 86, frequency_text, f10, MUTED)
    _text_right(draw, 455, 105, "60 sec", f8, MUTED)

    draw.text((260, 132), "RAM", font=f11, fill=WHITE)
    _text_right(draw, 455, 128, f"{snapshot.ram_percent:.0f}%", f20)
    draw_segment_bar(draw, (260, 149, 398, 156), snapshot.ram_percent)
    draw.text(
        (260, 158),
        f"{snapshot.ram_used_gb:.1f} / {snapshot.ram_total_gb:.0f} GiB",
        font=f8,
        fill=MUTED,
    )

    draw.text((260, 183), "SSD", font=f11, fill=WHITE)
    _text_right(draw, 455, 179, f"{snapshot.disk_percent:.0f}%", f20)
    draw_segment_bar(draw, (260, 200, 398, 207), snapshot.disk_percent)
    draw.text(
        (260, 209),
        f"{snapshot.disk_used_gb:.0f} / {snapshot.disk_total_gb:.0f} GB",
        font=f8,
        fill=MUTED,
    )

    # Compact three-column secondary metrics: spacious, elegant design with clean labels.
    summary = (14, 225, 468, 271)
    draw.rounded_rectangle(summary, radius=6, fill=PANEL, outline=BORDER)
    for x in (165, 317):
        draw.line([(x, 230), (x, 266)], fill=BORDER)

    # Column 1: GPU
    draw_chip(draw, 22, 234)
    draw.text((56, 229), "GPU", font=f9, fill=MUTED)
    gpu_text = "N/A" if snapshot.gpu_percent is None else f"{snapshot.gpu_percent:.0f}%"
    draw.text((56, 240), gpu_text, font=f14, fill=WHITE)
    gpu_sub = "NO SENSOR" if snapshot.gpu_percent is None else "UTILIZATION"
    draw.text((56, 257), gpu_sub, font=f8, fill=MUTED)

    # Column 2: LOAD 1M
    draw_load(draw, 173, 234)
    draw.text((207, 229), "LOAD 1M", font=f9, fill=MUTED)
    load_text = (
        "N/A"
        if snapshot.load_average_1m is None
        else f"{snapshot.load_average_1m:.2f}"
    )
    draw.text((207, 240), load_text, font=f14, fill=WHITE)
    draw.text((207, 257), "1 MIN AVG", font=f8, fill=MUTED)

    # Column 3: PROCS
    draw_terminal(draw, 325, 234)
    draw.text((359, 229), "PROCS", font=f9, fill=MUTED)
    process_text = "N/A" if snapshot.process_count <= 0 else str(snapshot.process_count)
    draw.text((359, 240), process_text, font=f14, fill=WHITE)
    draw.text((359, 257), "TOTAL ACTIVE", font=f8, fill=MUTED)

    # Bottom utility card.
    utility = (14, 276, 468, 314)
    draw.rounded_rectangle(utility, radius=6, fill=PANEL, outline=BORDER)
    for x in (165, 317):
        draw.line([(x, 282), (x, 308)], fill=BORDER)

    # Column 1: FAN
    fan_value, fan_status = format_fan(snapshot.fan_rpm)
    draw_fan(draw, 22, 281)
    draw.text((56, 280), "FAN", font=f9, fill=MUTED)
    draw.text((56, 291), fan_value, font=f11, fill=WHITE)
    draw.text((56, 303), fan_status, font=f8, fill=MUTED)

    # Column 2: TEMP
    draw_thermometer(draw, 173, 280)
    draw.text((207, 280), "TEMP", font=f9, fill=MUTED)
    draw.text((207, 291), format_temperature(snapshot), font=f11, fill=WHITE)
    current_temp = snapshot.cpu_temp_c if snapshot.cpu_temp_c is not None else snapshot.gpu_temp_c
    if current_temp is None:
        temp_status = "NO SENSOR"
    elif current_temp >= 88:
        temp_status = "HOT"
    elif current_temp >= 75:
        temp_status = "WARM"
    else:
        temp_status = "NORMAL"
    draw.text((207, 303), temp_status, font=f8, fill=MUTED)

    # Column 3: NETWORK
    draw.text((325, 280), "NETWORK", font=f9, fill=MUTED)
    draw_arrow(draw, 325, 294, "up")
    draw.text((342, 291), f"{format_rate(snapshot.net_up_mb_s)} MB/s", font=f9, fill=WHITE)
    draw_arrow(draw, 395, 294, "down")
    draw.text((412, 291), format_rate(snapshot.net_down_mb_s), font=f9, fill=WHITE)
    draw.text((412, 303), "MB/s", font=f8, fill=MUTED)
    return image


def _send_frame(transport, image, chunk_size):
    transport.write(build_command(DISPLAY_BITMAP, 0, 0, W - 1, H - 1), timeout_ms=1000)
    payload = image_to_rgb565le(image)
    for offset in range(0, len(payload), chunk_size):
        transport.write(payload[offset:offset + chunk_size], timeout_ms=2000)
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
    weather: WeatherCollector,
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
    LOG.info("TRUE VIEW 26 renderer started (%s, %s)", system_info.kind, system_info.model)

    while not stop_event.is_set():
        if max_frames is not None and frames >= max_frames:
            break
        snapshot = metrics.snapshot()
        if not history_initialized and snapshot.cpu_percent > 0:
            history = deque([snapshot.cpu_percent] * 60, maxlen=60)
            history_initialized = True
        else:
            history.append(snapshot.cpu_percent)
        frame = render_frame(
            config, snapshot, weather.snapshot(), system_info, history
        )
        _send_frame(transport, frame, config.device.chunk_size)
        frames += 1
        stop_event.wait(config.display.stats_interval)
