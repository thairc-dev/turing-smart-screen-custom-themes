from __future__ import annotations

from collections import deque
import math
import logging
from pathlib import Path
import time

from PIL import Image, ImageDraw, ImageFont

from .config import AppConfig
from .metrics import MetricsCollector, SystemInfo, display_model_name
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

W, H = 480, 320
LOG = logging.getLogger(__name__)

# Exact Concept Colors
BG = (7, 11, 25)
PANEL = (12, 19, 41)
BORDER = (26, 37, 66)
WHITE = (255, 255, 255)
GRAY_TEXT = (148, 163, 184)
CYAN = (0, 229, 255)
GREEN = (0, 230, 118)
PURPLE = (168, 85, 247)
BLUE = (59, 130, 246)
GOLD = (255, 209, 0)       # Bright concept sun yellow
SUN_RAY = (255, 193, 7)
ORANGE = (239, 68, 68)     # Concept red high thermometer (#EF4444)
BLUE_TEMP = (0, 176, 255)  # Concept cyan/blue low thermometer (#00B0FF)
DROPLET_BLUE = (0, 229, 255)# Concept bright cyan droplet (#00E5FF)
BAR_OFF = (25, 33, 52)
GRAPH_FILL = (9, 45, 20)


def _send_frame(transport: DisplayTransport, image: Image.Image, chunk_size: int) -> None:
    transport.write(build_command(DISPLAY_BITMAP, 0, 0, W - 1, H - 1), timeout_ms=1000)
    payload = image_to_rgb565le(image)
    for offset in range(0, len(payload), chunk_size):
        transport.write(payload[offset:offset + chunk_size], timeout_ms=2000)
        time.sleep(0.001)
    time.sleep(0.025)


def cleanse_display(transport: DisplayTransport, chunk_size: int) -> None:
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


# Vector Icon Helpers
def draw_display_icon(draw, x, y, color=GOLD):
    draw.rectangle([x, y, x + 18, y + 13], outline=color, width=1)
    draw.line([(x + 9, y + 13), (x + 9, y + 17)], fill=color, width=1)
    draw.line([(x + 5, y + 17), (x + 13, y + 17)], fill=color, width=1)


def draw_cpu_chip_icon(draw, x, y, color=GREEN):
    # Standardized 32x32 CPU Chip Icon centered at (x+16, y+16)
    cx, cy = x + 16, y + 16
    # Outer chip body 24x24
    draw.rectangle([cx - 12, cy - 12, cx + 12, cy + 12], outline=color, width=2)
    # Inner die 10x10
    draw.rectangle([cx - 5, cy - 5, cx + 5, cy + 5], outline=color, width=2)
    # 4 pins on each of 4 sides
    for offset in (-8, -3, 3, 8):
        draw.line([(cx + offset, cy - 16), (cx + offset, cy - 12)], fill=color, width=2)
        draw.line([(cx + offset, cy + 12), (cx + offset, cy + 16)], fill=color, width=2)
        draw.line([(cx - 16, cy + offset), (cx - 12, cy + offset)], fill=color, width=2)
        draw.line([(cx + 12, cy + offset), (cx + 16, cy + offset)], fill=color, width=2)


def draw_ram_stick_icon(draw, x, y, color=PURPLE):
    # Standardized 32x32 RAM Stick Icon centered at (x+16, y+16)
    cx, cy = x + 16, y + 16
    # Main RAM module board 30x20
    draw.rectangle([cx - 15, cy - 11, cx + 15, cy + 9], outline=color, width=2)
    # 3 Memory Chip Blocks inside
    for chip_x in (cx - 11, cx - 3, cx + 5):
        draw.rectangle([chip_x, cy - 7, chip_x + 6, cy + 3], outline=color, width=1)
    # Bottom connector pins
    for pin_x in range(cx - 13, cx + 15, 4):
        draw.line([(pin_x, cy + 9), (pin_x, cy + 14)], fill=color, width=2)


def draw_ssd_drive_icon(draw, x, y, color=BLUE, font_micro=None):
    # Standardized 32x32 SSD Drive Icon centered at (x+16, y+16)
    cx, cy = x + 16, y + 16
    # Outer SSD Drive Enclosure 26x30
    draw.rectangle([cx - 13, cy - 15, cx + 13, cy + 15], outline=color, width=2)
    # Controller / Label Area 20x14
    draw.rectangle([cx - 10, cy - 11, cx + 10, cy + 3], outline=color, width=1)
    if font_micro:
        w_ssd = draw.textlength("SSD", font=font_micro)
        draw.text((round(cx - w_ssd / 2), cy - 9), "SSD", fill=color, font=font_micro)
    # 2 Bottom Screw/SATA Ports
    draw.ellipse([cx - 8, cy + 7, cx - 4, cy + 11], fill=color)
    draw.ellipse([cx + 4, cy + 7, cx + 8, cy + 11], fill=color)


def draw_clock_circle_icon(draw, x, y, color=CYAN):
    draw.ellipse([x, y, x + 24, y + 24], outline=color, width=2)
    draw.line([(x + 12, y + 12), (x + 12, y + 6)], fill=color, width=2)
    draw.line([(x + 12, y + 12), (x + 17, y + 17)], fill=color, width=2)


def draw_up_arrow(draw, x, y, color=CYAN):
    draw.polygon([(x + 3, y), (x, y + 5), (x + 6, y + 5)], fill=color)
    draw.line([(x + 3, y + 5), (x + 3, y + 9)], fill=color, width=2)


def draw_down_arrow(draw, x, y, color=GREEN):
    draw.line([(x + 3, y), (x + 3, y + 4)], fill=color, width=2)
    draw.polygon([(x, y + 4), (x + 6, y + 4), (x + 3, y + 9)], fill=color)


def draw_wifi_arc_icon(draw, x, y, color=CYAN):
    cx, cy = x + 13, y + 18
    draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=color)
    for r in (7, 12, 17):
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(bbox, start=-135, end=-45, fill=color, width=2)


def draw_thermometer_icon(draw, x, y, color=ORANGE):
    # Bottom Utility Bar Thermometer with 3 heat wave dots on upper right
    cx = x + 9
    draw.rounded_rectangle([cx - 4, y + 2, cx + 4, y + 18], radius=4, outline=color, width=2)
    draw.ellipse([cx - 7, y + 15, cx + 7, y + 28], outline=color, width=2)
    draw.ellipse([cx - 4, y + 18, cx + 4, y + 25], fill=color)
    draw.line([(cx, y + 8), (cx, y + 18)], fill=color, width=2)
    draw.rectangle([cx + 6, y + 4, cx + 7, y + 5], fill=color)
    draw.rectangle([cx + 6, y + 8, cx + 7, y + 9], fill=color)
    draw.rectangle([cx + 6, y + 12, cx + 7, y + 13], fill=color)


def draw_small_thermometer_icon(draw, x, y, color=ORANGE):
    # Slender 8px wide 1px thermometer
    cx = x + 4
    draw.rectangle([cx - 2, y, cx + 2, y + 10], outline=color, width=1)
    draw.ellipse([cx - 4, y + 8, cx + 4, y + 16], outline=color, width=1)
    draw.ellipse([cx - 2, y + 10, cx + 2, y + 14], fill=color)
    draw.line([(cx, y + 4), (cx, y + 11)], fill=color, width=1)


def draw_hollow_droplet_icon(draw, x, y, color=DROPLET_BLUE):
    # Slender 8px wide 1px teardrop
    cx = x + 4
    draw.line([(cx, y), (cx - 4, y + 8)], fill=color, width=1)
    draw.line([(cx, y), (cx + 4, y + 8)], fill=color, width=1)
    draw.ellipse([cx - 4, y + 6, cx + 4, y + 16], outline=color, width=1)


FAN_ICON_ASSET_PATH = Path(__file__).parent / "assets" / "fan_icon.png"
_FAN_ICON_CACHE: Image.Image | None | bool = None

def _get_fan_icon_asset() -> Image.Image | None:
    global _FAN_ICON_CACHE
    if _FAN_ICON_CACHE is None:
        if FAN_ICON_ASSET_PATH.exists():
            try:
                _FAN_ICON_CACHE = Image.open(FAN_ICON_ASSET_PATH).convert("RGBA")
            except Exception:
                _FAN_ICON_CACHE = False
        else:
            _FAN_ICON_CACHE = False
    return _FAN_ICON_CACHE if isinstance(_FAN_ICON_CACHE, Image.Image) else None


def draw_fan_blade_icon(draw, x, y, color=WHITE, image: Image.Image | None = None):
    asset = _get_fan_icon_asset()
    if asset and image:
        image.paste(asset, (x, y), asset)
        return

    # Fallback vector fan
    cx, cy = x + 14, y + 14
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], outline=color, width=1)
    for i in range(4):
        base_angle = i * 90
        rad = math.radians(base_angle + 45)
        bcx = cx + 5.5 * math.cos(rad)
        bcy = cy + 5.5 * math.sin(rad)
        r = 8.5
        draw.arc([bcx - r, bcy - r, bcx + r, bcy + r],
                 start=base_angle + 90, end=base_angle + 270, fill=color, width=1)


def draw_weather_icon(draw, x, y, condition: str):
    sun_cx, sun_cy = x + 24, y + 12
    draw.ellipse([sun_cx - 7, sun_cy - 7, sun_cx + 7, sun_cy + 7], fill=GOLD)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = round(sun_cx + 9 * math.cos(rad))
        y1 = round(sun_cy + 9 * math.sin(rad))
        x2 = round(sun_cx + 13 * math.cos(rad))
        y2 = round(sun_cy + 13 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=SUN_RAY, width=2)

    cloud_color = WHITE
    shadow_color = (225, 232, 240)
    draw.rectangle([x + 5, y + 22, x + 27, y + 31], fill=shadow_color)
    draw.ellipse([x + 1, y + 18, x + 14, y + 31], fill=shadow_color)
    draw.ellipse([x + 9, y + 13, x + 23, y + 31], fill=shadow_color)
    draw.ellipse([x + 16, y + 18, x + 31, y + 31], fill=shadow_color)

    draw.rectangle([x + 5, y + 20, x + 27, y + 29], fill=cloud_color)
    draw.ellipse([x + 1, y + 16, x + 14, y + 29], fill=cloud_color)
    draw.ellipse([x + 9, y + 11, x + 23, y + 29], fill=cloud_color)
    draw.ellipse([x + 16, y + 16, x + 31, y + 29], fill=cloud_color)


def draw_scaled_wave_graph(draw, box, history, line_color=GREEN, fill_color=GRAPH_FILL, font_nano=None, right_x=454):
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    if not history or w <= 0 or h <= 0:
        return

    values = list(history)
    num = len(values)
    points = []
    for i, val in enumerate(values):
        px = round(x0 + (i / max(1, num - 1)) * w)
        py = round(y1 - ((max(0.0, min(100.0, float(val))) / 100.0) * (h - 2)))
        points.append((px, py))

    if len(points) >= 2:
        poly_pts = points + [(x1, y1), (x0, y1)]
        draw.polygon(poly_pts, fill=fill_color)
        draw.line(points, fill=line_color, width=2)

    if font_nano:
        for lbl, py_pos in [("100%", y0 - 2), ("50%", y0 + h // 2 - 4), ("0%", y1 - 6)]:
            w_lbl = draw.textlength(lbl, font=font_nano)
            draw.text((right_x - w_lbl, py_pos), lbl, fill=GRAY_TEXT, font=font_nano)


def draw_mini_wave_graph(draw, box, history, line_color=ORANGE):
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    if not history or w <= 0 or h <= 0:
        return

    values = list(history)
    num = len(values)
    points = []
    for i, val in enumerate(history):
        px = round(x0 + (i / max(1, num - 1)) * w)
        py = round(y1 - ((max(0.0, min(100.0, float(val))) / 100.0) * (h - 2)))
        points.append((px, py))

    if len(points) >= 2:
        draw.line(points, fill=line_color, width=2)


def draw_10_segment_rgb_pill_bar(draw, box, percent, active_color=PURPLE):
    x0, y0, x1, y1 = box
    total_segments = 10
    gap = 3
    seg_w = ((x1 - x0) - (gap * (total_segments - 1))) // total_segments
    active_count = round((max(0.0, min(100.0, percent)) / 100.0) * total_segments)

    for i in range(total_segments):
        sx0 = x0 + i * (seg_w + gap)
        sx1 = sx0 + seg_w
        seg_color = active_color if i < active_count else BAR_OFF
        draw.rounded_rectangle([sx0, y0, sx1, y1], radius=2, fill=seg_color)


def format_uptime(uptime_seconds: int) -> str:
    seconds = max(0, uptime_seconds)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"


def format_rate(rate_mb_s: float) -> str:
    rate = max(0.0, rate_mb_s)
    if rate < 100:
        return f"{rate:.1f}"
    if rate < 1000:
        return f"{rate:.0f}"
    return f"{min(99.9, rate / 1000):.1f}K"


def render_frame(
    config: AppConfig,
    snapshot,
    weather_snapshot,
    system_info: SystemInfo,
    cpu_history: list[float],
    temp_history: list[float],
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(image)

    fTitle = fonts["fTitle"]
    fClock = fonts["fClock"]
    fHeaderTime = fonts["fHeaderTime"]
    fBigVal = fonts["fBigVal"]
    fWeatherTemp = fonts["fWeatherTemp"]
    fWeatherCond = fonts["fWeatherCond"]
    fCardVal = fonts["fCardVal"]
    fMedium = fonts["fMedium"]
    fSmall = fonts["fSmall"]
    fMicro = fonts["fMicro"]
    fNano = fonts["fNano"]

    real_model = display_model_name(system_info, max_chars=18)
    real_os = system_info.os_version

    # ── 1. RIGHT COMPONENT CARDS ──
    # CPU Card
    d.rounded_rectangle([196, 10, 468, 80], radius=6, fill=(9, 26, 16), outline=BORDER, width=1)
    d.rounded_rectangle([196, 10, 202, 80], radius=3, fill=GREEN) # Solid left accent strip
    draw_cpu_chip_icon(d, 212, 29, GREEN)
    d.line([(254, 14), (254, 76)], fill=BORDER, width=1)
    d.text((264, 14), "CPU", fill=WHITE, font=fTitle)
    cpu = int(snapshot.cpu_percent)
    freq_str = f"{snapshot.cpu_freq_ghz:.1f} GHz"
    d.text((264, 32), f"{cpu}%", fill=GREEN, font=fBigVal)
    w_freq = d.textlength(freq_str, font=fMedium)
    d.text((454 - w_freq, 14), freq_str, fill=WHITE, font=fMedium)
    draw_scaled_wave_graph(d, [348, 32, 424, 72], cpu_history, line_color=GREEN, fill_color=(9, 45, 20), font_nano=fNano, right_x=454)

    # RAM Card
    d.rounded_rectangle([196, 90, 468, 160], radius=6, fill=(22, 8, 38), outline=BORDER, width=1)
    d.rounded_rectangle([196, 90, 202, 160], radius=3, fill=PURPLE) # Solid left accent strip
    draw_ram_stick_icon(d, 212, 109, PURPLE)
    d.line([(254, 94), (254, 156)], fill=BORDER, width=1)
    d.text((264, 94), "RAM", fill=WHITE, font=fTitle)
    rp = int(snapshot.ram_percent)
    rg = snapshot.ram_used_gb
    rt = snapshot.ram_total_gb
    ram_str = f"{rg:.1f} / {rt:.0f} GB"
    d.text((264, 112), f"{rp}%", fill=PURPLE, font=fBigVal)
    w_ram = d.textlength(ram_str, font=fMedium)
    d.text((454 - w_ram, 94), ram_str, fill=WHITE, font=fMedium)
    draw_10_segment_rgb_pill_bar(d, [348, 122, 454, 144], rp, active_color=PURPLE)

    # SSD Card
    d.rounded_rectangle([196, 170, 468, 240], radius=6, fill=(11, 21, 48), outline=BORDER, width=1)
    d.rounded_rectangle([196, 170, 202, 240], radius=3, fill=BLUE) # Solid left accent strip
    draw_ssd_drive_icon(d, 212, 189, BLUE, font_micro=fMicro)
    d.line([(254, 174), (254, 236)], fill=BORDER, width=1)
    d.text((264, 174), "SSD", fill=WHITE, font=fTitle)
    dp = int(snapshot.disk_percent)
    du = snapshot.disk_used_gb
    dt2 = snapshot.disk_total_gb
    ssd_str = f"{du:.0f} / {dt2:.0f} GB"
    d.text((264, 192), f"{dp}%", fill=BLUE, font=fBigVal)
    w_ssd = d.textlength(ssd_str, font=fMedium)
    d.text((454 - w_ssd, 174), ssd_str, fill=WHITE, font=fMedium)
    draw_10_segment_rgb_pill_bar(d, [348, 202, 454, 224], dp, active_color=BLUE)

    # ── 2. TOP LEFT HEADER & GIANT DIGITAL CLOCK ──
    draw_display_icon(d, 14, 12, GOLD)
    d.text((40, 8), real_model, fill=WHITE, font=fTitle)
    d.text((40, 24), real_os, fill=(124, 139, 161), font=fSmall)

    # Modern Tall Bold Digital Clock
    time_str = time.strftime("%H:%M")
    w_clock = d.textlength(time_str, font=fClock)
    x_clock = 12 + int((172 - w_clock) / 2)
    d.text((x_clock, 42), time_str, fill=WHITE, font=fClock)

    # Horizontal Divider Line
    d.line([(16, 122), (184, 122)], fill=BORDER, width=1)

    # Date Row
    day_abbr = time.strftime("%a").upper()
    day_num = time.strftime("%d")
    month_name = time.strftime("%b").upper()
    year_str = time.strftime("%Y")

    w1 = d.textlength(day_abbr, font=fHeaderTime)
    w2 = d.textlength(day_num, font=fHeaderTime)
    w3 = d.textlength(month_name, font=fHeaderTime)
    w4 = d.textlength(year_str, font=fHeaderTime)

    gap = 14  # Concept word gap
    total_txt_w = w1 + gap + w2 + gap + w3 + gap + w4
    x1 = 12 + (172 - total_txt_w) // 2
    x2 = x1 + w1 + gap
    x3 = x2 + w2 + gap
    x4 = x3 + w3 + gap

    d.text((round(x1), 132), day_abbr, fill=GOLD, font=fHeaderTime)
    d.text((round(x2), 132), day_num, fill=WHITE, font=fHeaderTime)
    d.text((round(x3), 132), month_name, fill=WHITE, font=fHeaderTime)
    d.text((round(x4), 132), year_str, fill=WHITE, font=fHeaderTime)

    # ── 3. BOTTOM LEFT WEATHER CARD (Icon X=147, Text X=159 -> Perfectly Centered & Balanced Margins!) ──
    d.rounded_rectangle([12, 166, 184, 240], radius=6, fill=(10, 22, 43), outline=BORDER, width=1)
    d.line([(142, 170), (142, 236)], fill=BORDER, width=1)

    # Left Sub-panel: 3D Sun/Cloud Icon (X=22) + 32°C (X=66) + PARTLY CLOUDY (X=66)
    draw_weather_icon(d, 22, 184, weather_snapshot.condition)
    d.text((66, 176), weather_snapshot.temperature, fill=WHITE, font=fWeatherTemp)
    d.text((66, 216), weather_snapshot.description.upper(), fill=(116, 169, 216), font=fWeatherCond)

    # Right Sub-panel: Icon X=145 (Width 8px -> 153), Text X=161 (8px Gap!)
    draw_small_thermometer_icon(d, 145, 174, ORANGE)
    d.text((161, 176), weather_snapshot.high_c, fill=WHITE, font=fMedium)

    draw_small_thermometer_icon(d, 145, 196, BLUE_TEMP)
    d.text((161, 198), weather_snapshot.low_c, fill=WHITE, font=fMedium)

    draw_hollow_droplet_icon(d, 145, 218, DROPLET_BLUE)
    d.text((161, 220), weather_snapshot.humidity, fill=WHITE, font=fMedium)

    # ── 4. FULL WIDTH BOTTOM UTILITY BAR ──
    d.rounded_rectangle([12, 250, 468, 310], radius=6, fill=PANEL, outline=BORDER, width=1)
    for div_x in [104, 196, 288, 380]:
        d.line([(div_x, 256), (div_x, 304)], fill=BORDER, width=1)

    # Column 1: UPTIME (X=12..104)
    draw_clock_circle_icon(d, 20, 267, CYAN)
    d.text((52, 260), "UPTIME", fill=WHITE, font=fMedium)
    # Split uptime into 2 lines to avoid overflow past X=104
    _up = max(0, snapshot.uptime_seconds)
    _d, _h, _m = _up // 86400, (_up % 86400) // 3600, (_up % 3600) // 60
    _uptime_line1 = f"{_d}d {_h}h"
    _uptime_line2 = f"{_m}m"
    d.text((52, 274), _uptime_line1, fill=CYAN, font=fMicro)
    d.text((52, 288), _uptime_line2, fill=CYAN, font=fMicro)

    # Column 2: NETWORK (X=104..196)
    draw_down_arrow(d, 112, 258, GREEN)
    dn_str = format_rate(snapshot.net_down_mb_s)
    d.text((122, 256), dn_str, fill=WHITE, font=fCardVal)
    w_dn = d.textlength(dn_str, font=fCardVal)
    d.text((round(122 + w_dn + 2), 258), "MB/s", fill=GRAY_TEXT, font=fNano)

    draw_up_arrow(d, 112, 274, CYAN)
    up_str = format_rate(snapshot.net_up_mb_s)
    d.text((122, 272), up_str, fill=WHITE, font=fCardVal)
    w_up = d.textlength(up_str, font=fCardVal)
    d.text((round(122 + w_up + 2), 274), "MB/s", fill=GRAY_TEXT, font=fNano)

    w_net = d.textlength("NETWORK", font=fMedium)
    d.text((104 + int((92 - w_net) / 2), 290), "NETWORK", fill=WHITE, font=fMedium)

    # Column 3: WiFi / IP (X=196..288)
    draw_wifi_arc_icon(d, 202, 258, CYAN)
    wifi_disp = snapshot.wifi_name[:9] if len(snapshot.wifi_name) > 9 else snapshot.wifi_name
    d.text((232, 260), wifi_disp, fill=WHITE, font=fMedium)

    ip_str = snapshot.ip_address
    w_ip = d.textlength(ip_str, font=fCardVal)
    d.text((196 + int((92 - w_ip) / 2), 284), ip_str, fill=CYAN, font=fCardVal)

    # Column 4: TEMP (X=288..380)
    draw_thermometer_icon(d, 296, 258, ORANGE)
    d.text((324, 258), "TEMP", fill=WHITE, font=fMedium)
    cpu_temp = "--" if snapshot.cpu_temp_c is None else f"{snapshot.cpu_temp_c:.0f}°C"
    d.text((324, 270), cpu_temp, fill=ORANGE, font=fHeaderTime)
    draw_mini_wave_graph(d, [294, 298, 372, 306], temp_history, line_color=ORANGE)

    # Column 5: FAN (X=380..468, Start X=415)
    draw_fan_blade_icon(d, 386, 264, WHITE, image=image)
    d.text((415, 258), "FAN", fill=WHITE, font=fMedium)
    fan_rpm = snapshot.fan_rpm
    if fan_rpm is None:
        d.text((415, 268), "N/A", fill=(140, 140, 140), font=fMicro)
        d.text((415, 290), "NO SENSOR", fill=(120, 120, 120), font=fNano)
    else:
        fan_status = "SILENT" if fan_rpm == 0 else "ACTIVE"
        rpm_str = str(fan_rpm)
        if len(rpm_str) <= 2:
            d.text((415, 270), rpm_str, fill=WHITE, font=fHeaderTime)
            d.text((426, 274), "RPM", fill=WHITE, font=fNano)
        else:
            d.text((415, 272), f"{rpm_str} RPM", fill=WHITE, font=fMicro)
        d.text((415, 290), fan_status, fill=(160, 190, 220), font=fNano)

    return image


def render_session(
    config: AppConfig,
    transport: DisplayTransport,
    metrics: MetricsCollector,
    weather: WeatherCollector,
    system_info: SystemInfo,
    stop_event,
    max_frames: int | None = None,
) -> None:
    if config.display.clean_on_startup:
        LOG.info("Clearing native portrait GRAM before landscape render")
        cleanse_display(transport, config.device.chunk_size)

    transport.write(build_command(SCREEN_ON))
    brightness_value = int(255 - config.display.brightness * 2.55)
    transport.write(build_command(SET_BRIGHTNESS, brightness_value, 0, 0, 0))
    transport.write(orientation_command(W, H))
    time.sleep(0.2)

    black_font = config.fonts_dir / "Roboto-Black.ttf"
    bold_font = config.fonts_dir / "Roboto-Bold.ttf"
    regular_font = config.fonts_dir / "Roboto-Regular.ttf"
    try:
        fTitle = ImageFont.truetype(str(bold_font), 14)
        fClock = ImageFont.truetype(str(black_font), 64)
        fHeaderTime = ImageFont.truetype(str(bold_font), 14)
        fBigVal = ImageFont.truetype(str(black_font), 34)
        fWeatherTemp = ImageFont.truetype(str(black_font), 30)
        fWeatherCond = ImageFont.truetype(str(bold_font), 10)
        fCardVal = ImageFont.truetype(str(bold_font), 11)
        fMedium = ImageFont.truetype(str(bold_font), 10)
        fSmall = ImageFont.truetype(str(regular_font), 10)
        fMicro = ImageFont.truetype(str(bold_font), 9)
        fNano = ImageFont.truetype(str(regular_font), 8)
    except OSError as exc:
        LOG.warning("Could not load bundled fonts: %s", exc)
        fTitle = fClock = fHeaderTime = fBigVal = fWeatherTemp = fWeatherCond = fCardVal = fMedium = fSmall = fMicro = fNano = ImageFont.load_default()

    fonts = {
        "fTitle": fTitle,
        "fClock": fClock,
        "fHeaderTime": fHeaderTime,
        "fBigVal": fBigVal,
        "fWeatherTemp": fWeatherTemp,
        "fWeatherCond": fWeatherCond,
        "fCardVal": fCardVal,
        "fMedium": fMedium,
        "fSmall": fSmall,
        "fMicro": fMicro,
        "fNano": fNano,
    }

    initial_snapshot = metrics.snapshot()
    cpu_history = [initial_snapshot.cpu_percent] * 24
    initial_temp = initial_snapshot.cpu_temp_c if initial_snapshot.cpu_temp_c is not None else 0.0
    temp_history = [initial_temp] * 24
    frame_count = 0

    LOG.info("APEX 01 renderer started (%s, %s)", system_info.kind, system_info.model)

    while not stop_event.is_set():
        if max_frames is not None and frame_count >= max_frames:
            break
        frame_count += 1

        snapshot = metrics.snapshot()
        weather_snapshot = weather.snapshot()

        cpu_history.append(snapshot.cpu_percent)
        if len(cpu_history) > 24:
            cpu_history.pop(0)

        current_temp = snapshot.cpu_temp_c if snapshot.cpu_temp_c is not None else 0.0
        temp_history.append(current_temp)
        if len(temp_history) > 24:
            temp_history.pop(0)

        img = render_frame(
            config,
            snapshot,
            weather_snapshot,
            system_info,
            cpu_history,
            temp_history,
            fonts,
        )

        _send_frame(transport, img, config.device.chunk_size)
        stop_event.wait(config.display.stats_interval)
