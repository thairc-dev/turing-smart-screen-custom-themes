import time
import math
import logging
from collections import deque
from PIL import Image, ImageDraw, ImageFont

from .config import AppConfig
from .metrics import MetricsCollector, SystemInfo, display_model_name
from .protocol import CLEAR, DISPLAY_BITMAP, SCREEN_OFF, SCREEN_ON, SET_BRIGHTNESS, build_command, image_to_rgb565le, orientation_command
from .transports.base import DisplayTransport
from .weather import WeatherCollector

W, H = 480, 320
LOG = logging.getLogger(__name__)

# Colors matching concept 100% (PURE BLACK PANELS, NO BLUE)
BG = (0, 0, 0)              # Absolute Pitch Black #000000
CARD_BG = (10, 12, 18)      # Dark Charcoal Black #0A0C12 (NOT BLUE)
CARD_BORDER = (24, 28, 40)  # Dark Charcoal Border #181C28
TEXT_WHITE = (255, 255, 255)
TEXT_MUTED = (148, 163, 184)# Slate Gray #94A3B8

CYAN = (0, 229, 255)        # #00E5FF Cyan Accent
PURPLE = (168, 85, 247)     # #A855F7 Purple Accent
BLUE = (59, 130, 246)       # #3B82F6 Blue Accent
ORANGE = (255, 85, 51)      # #FF5533 Glowing Orange Temp
BLUE_TEMP = (96, 165, 250)  # #60A5FA Low Temp


def write_stream(
    transport: DisplayTransport,
    data: bytes,
    chunk_size: int,
    timeout_ms: int = 1000,
) -> None:
    view = memoryview(data)
    for offset in range(0, len(view), chunk_size):
        transport.write(view[offset:offset + chunk_size], timeout_ms=timeout_ms)
        if len(view) > chunk_size:
            time.sleep(0.001)


def send_full_frame(
    transport: DisplayTransport,
    image: Image.Image,
    chunk_size: int,
) -> None:
    transport.write(build_command(DISPLAY_BITMAP, 0, 0, W - 1, H - 1), timeout_ms=1000)
    write_stream(transport, image_to_rgb565le(image), chunk_size)
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
    send_full_frame(transport, black, chunk_size)


# Arc gauge for percentage
def draw_arc_gauge(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], percent: float, color: tuple[int, int, int]):
    x0, y0, x1, y1 = box
    draw.ellipse([x0, y0, x1, y1], outline=(24, 28, 40), width=4)
    if percent > 0:
        angle = min(360, int((percent / 100.0) * 360))
        draw.arc([x0, y0, x1, y1], start=-90, end=-90 + angle, fill=color, width=4)


# Segmented progress bar
def draw_segment_bar(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], percent: float, color: tuple[int, int, int]):
    x0, y0, x1, y1 = box
    total_segments = 12
    gap = 2
    seg_w = ((x1 - x0) - (gap * (total_segments - 1))) // total_segments
    active_count = max(0, min(total_segments, int(round((percent / 100.0) * total_segments))))

    for i in range(total_segments):
        sx0 = x0 + i * (seg_w + gap)
        sx1 = sx0 + seg_w
        seg_color = color if i < active_count else (20, 24, 34)
        draw.rectangle([sx0, y0, sx1, y1], fill=seg_color)


# Glowing wave graph with subtle gradient glow underneath (Matching concept 100%)
def draw_glowing_wave_graph(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], history: deque | list, line_color: tuple[int, int, int]):
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    if len(history) < 2 or w <= 0 or h <= 0:
        return

    num = len(history)
    line_pts = []
    for i, val in enumerate(history):
        px = x0 + int((i / (num - 1)) * w)
        py = y1 - int(((max(0.0, min(100.0, float(val))) / 100.0) * (h - 2)))
        py = max(y0, min(y1, py))
        line_pts.append((px, py))

    # Soft gradient glow fade under the line
    r, g, b = line_color
    for px, py in line_pts:
        glow_len = y1 - py
        if glow_len > 0:
            for step in range(glow_len):
                alpha = 0.35 * (1.0 - (step / max(1, glow_len)))
                gr = max(0, min(255, int(r * alpha)))
                gg = max(0, min(255, int(g * alpha)))
                gb = max(0, min(255, int(b * alpha)))
                draw.point((px, py + step), fill=(gr, gg, gb))

    # Crisp stroke line on top
    draw.line(line_pts, fill=line_color, width=1)


# Vector Arrow UP (Cyan)
def draw_up_arrow(draw: ImageDraw.ImageDraw, x: int, y: int, color=CYAN):
    draw.line([(x + 3, y + 9), (x + 3, y)], fill=color, width=2)
    draw.line([(x, y + 4), (x + 3, y), (x + 6, y + 4)], fill=color, width=2)


# Vector Arrow DOWN (Purple)
def draw_down_arrow(draw: ImageDraw.ImageDraw, x: int, y: int, color=PURPLE):
    draw.line([(x + 3, y), (x + 3, y + 9)], fill=color, width=2)
    draw.line([(x, y + 5), (x + 3, y + 9), (x + 6, y + 5)], fill=color, width=2)


# Computer Icon
def draw_computer_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=TEXT_WHITE):
    draw.rectangle([x, y, x + 20, y + 13], outline=color, width=2)
    draw.line([(x + 6, y + 14), (x + 14, y + 14)], fill=color, width=2)
    draw.line([(x + 3, y + 16), (x + 17, y + 16)], fill=color, width=2)


# Crisp Wi-Fi Signal Icon (3 Arcs + Center Dot)
def draw_wifi_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=TEXT_WHITE):
    draw.arc([x, y, x + 16, y + 16], 225, 315, fill=color, width=2)
    draw.arc([x + 3, y + 3, x + 13, y + 13], 225, 315, fill=color, width=2)
    draw.ellipse([x + 7, y + 10, x + 9, y + 12], fill=color)


# Main Weather Icon (32x28px, perfectly balanced)
def draw_huge_weather_icon(draw: ImageDraw.ImageDraw, x: int, y: int, condition: str):
    sun_yellow = (250, 184, 0)     # Vibrant Sun Yellow #FAB800
    cloud_white = (255, 255, 255) # Crisp White #FFFFFF

    # Sun peeking top-right behind cloud
    sun_cx, sun_cy = x + 20, y + 8
    r = 5
    draw.ellipse([sun_cx - r, sun_cy - r, sun_cx + r, sun_cy + r], outline=sun_yellow, width=2)
    for a in range(210, 390, 45):
        rad = math.radians(a)
        x1 = sun_cx + int(7 * math.cos(rad))
        y1 = sun_cy + int(7 * math.sin(rad))
        x2 = sun_cx + int(10 * math.cos(rad))
        y2 = sun_cy + int(10 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=sun_yellow, width=2)

    # Cloud in front
    draw.ellipse([x, y + 10, x + 14, y + 26], outline=cloud_white, width=2)
    draw.ellipse([x + 6, y + 5, x + 22, y + 26], outline=cloud_white, width=2)
    draw.ellipse([x + 14, y + 10, x + 28, y + 26], outline=cloud_white, width=2)
    draw.rectangle([x + 5, y + 14, x + 23, y + 26], fill=CARD_BG)
    draw.line([(x + 3, y + 26), (x + 25, y + 26)], fill=cloud_white, width=2)


def draw_weather_icon(draw: ImageDraw.ImageDraw, x: int, y: int, condition: str, scale=1.0):
    sun = (250, 204, 21)          # Yellow Sun #FACC15
    cloud_white = (255, 255, 255) # White Cloud #FFFFFF
    rain_blue = (96, 165, 250)    # Rain Drop Blue #60A5FA

    if condition in ("clear", "sun"):
        r = int(5 * scale)
        cx, cy = x + int(10 * scale), y + int(10 * scale)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=sun, fill=sun, width=1)
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x1 = cx + int((r + 2) * math.cos(rad))
            y1 = cy + int((r + 2) * math.sin(rad))
            x2 = cx + int((r + 5) * math.cos(rad))
            y2 = cy + int((r + 5) * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=sun, width=2)
    elif condition == "rain":
        draw.ellipse([x + int(2 * scale), y + int(4 * scale), x + int(10 * scale), y + int(12 * scale)], outline=cloud_white, width=2)
        draw.ellipse([x + int(6 * scale), y + int(1 * scale), x + int(16 * scale), y + int(12 * scale)], outline=cloud_white, width=2)
        draw.ellipse([x + int(12 * scale), y + int(4 * scale), x + int(20 * scale), y + int(12 * scale)], outline=cloud_white, width=2)
        draw.rectangle([x + int(5 * scale), y + int(6 * scale), x + int(17 * scale), y + int(12 * scale)], fill=CARD_BG)
        draw.line([(x + int(4 * scale), y + int(12 * scale)), (x + int(18 * scale), y + int(12 * scale))], fill=cloud_white, width=2)
        for dx in (5, 10, 15):
            draw.line([(x + int(dx * scale), y + int(14 * scale)), (x + int((dx - 2) * scale), y + int(18 * scale))], fill=rain_blue, width=2)
    elif condition == "cloudy":
        draw.ellipse([x + int(2 * scale), y + int(4 * scale), x + int(10 * scale), y + int(12 * scale)], outline=cloud_white, width=2)
        draw.ellipse([x + int(6 * scale), y + int(1 * scale), x + int(16 * scale), y + int(12 * scale)], outline=cloud_white, width=2)
        draw.ellipse([x + int(12 * scale), y + int(4 * scale), x + int(20 * scale), y + int(12 * scale)], outline=cloud_white, width=2)
        draw.rectangle([x + int(5 * scale), y + int(6 * scale), x + int(17 * scale), y + int(12 * scale)], fill=CARD_BG)
        draw.line([(x + int(4 * scale), y + int(12 * scale)), (x + int(18 * scale), y + int(12 * scale))], fill=cloud_white, width=2)
    else: # partly_cloudy
        sun_cx = x + int(15 * scale)
        sun_cy = y + int(6 * scale)
        r = int(4 * scale)
        draw.ellipse([sun_cx - r, sun_cy - r, sun_cx + r, sun_cy + r], outline=sun, fill=sun, width=1)
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x1 = sun_cx + int((r + 1) * math.cos(rad))
            y1 = sun_cy + int((r + 1) * math.sin(rad))
            x2 = sun_cx + int((r + 4) * math.cos(rad))
            y2 = sun_cy + int((r + 4) * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=sun, width=1)

        draw.ellipse([x + int(1 * scale), y + int(8 * scale), x + int(9 * scale), y + int(16 * scale)], outline=cloud_white, width=2)
        draw.ellipse([x + int(5 * scale), y + int(5 * scale), x + int(15 * scale), y + int(16 * scale)], outline=cloud_white, width=2)
        draw.ellipse([x + int(11 * scale), y + int(8 * scale), x + int(19 * scale), y + int(16 * scale)], outline=cloud_white, width=2)
        draw.rectangle([x + int(4 * scale), y + int(10 * scale), x + int(16 * scale), y + int(16 * scale)], fill=CARD_BG)
        draw.line([(x + 3), y + int(16 * scale), x + int(17 * scale), y + int(16 * scale)], fill=cloud_white, width=2)


def draw_mini_thermometer(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple[int, int, int]):
    draw.rectangle([x + 3, y + 1, x + 6, y + 8], outline=color, width=1)
    draw.ellipse([x + 1, y + 7, x + 8, y + 14], fill=color)


def draw_droplet_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=TEXT_WHITE):
    pts = [(x + 4, y + 1), (x + 1, y + 7), (x + 1, y + 11), (x + 4, y + 13), (x + 7, y + 11), (x + 7, y + 7)]
    draw.polygon(pts, outline=color, fill=None)


def draw_fan_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=TEXT_MUTED):
    cx, cy = x + 12, y + 12
    draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], outline=color, width=1)
    for a in [0, 90, 180, 270]:
        rad = math.radians(a)
        rad2 = math.radians(a + 45)
        x1 = cx + 4 * math.cos(rad)
        y1 = cy + 4 * math.sin(rad)
        x2 = cx + 11 * math.cos(rad2)
        y2 = cy + 11 * math.sin(rad2)
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)


def draw_thermometer_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=ORANGE):
    draw.rectangle([x + 5, y + 2, x + 9, y + 10], outline=color, width=2)
    draw.ellipse([x + 3, y + 9, x + 11, y + 17], fill=color)
    for dy in (4, 7, 10):
        draw.point((x + 13, y + dy), fill=color)


def draw_clock_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=CYAN):
    draw.ellipse([x, y, x + 18, y + 18], outline=color, width=2)
    draw.line([(x + 9, y + 9), (x + 9, y + 4)], fill=color, width=2)
    draw.line([(x + 9, y + 9), (x + 13, y + 9)], fill=color, width=2)


def draw_pulse_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color=TEXT_WHITE):
    draw.line([(x, y + 9), (x + 4, y + 9), (x + 7, y + 2), (x + 11, y + 16), (x + 15, y + 6), (x + 18, y + 9), (x + 22, y + 9)], fill=color, width=2)


def format_rate(rate_mb_s: float) -> str:
    rate = max(0.0, rate_mb_s)
    if rate < 100:
        return f"{rate:.1f}"
    if rate < 1000:
        return f"{rate:.0f}"
    return f"{min(99.9, rate / 1000):.1f}K"


def format_uptime(seconds: int) -> str:
    s = max(0, seconds)
    d = s // 86400
    h = (s % 86400) // 3600
    m = (s % 3600) // 60
    return f"{d}d {h}h {m}m"


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

    bold_font = config.fonts_dir / "Roboto-Bold.ttf"
    regular_font = config.fonts_dir / "Roboto-Regular.ttf"
    try:
        fClock = ImageFont.truetype(str(bold_font), 52)
        fWeatherTemp = ImageFont.truetype(str(bold_font), 24)
        fBigVal = ImageFont.truetype(str(bold_font), 20)
        fTitle = ImageFont.truetype(str(bold_font), 13)
        fDate = ImageFont.truetype(str(bold_font), 11)
        fMedium = ImageFont.truetype(str(bold_font), 11)
        fSmall = ImageFont.truetype(str(regular_font), 10)
        fMicro = ImageFont.truetype(str(regular_font), 9)
        fNano = ImageFont.truetype(str(regular_font), 8)
    except OSError as exc:
        LOG.warning("Could not load bundled fonts: %s", exc)
        fClock = fWeatherTemp = fBigVal = fTitle = fDate = fMedium = fSmall = fMicro = fNano = ImageFont.load_default()

    initial = metrics.snapshot()
    cpu_history = deque([initial.cpu_percent] * 30, maxlen=30)
    temp_history = deque([initial.cpu_temp_c if initial.cpu_temp_c is not None else 0.0] * 30, maxlen=30)
    procs_history = deque([initial.process_count] * 30, maxlen=30)
    uptime_history = deque([0.0] * 30, maxlen=30)

    frames = 0
    LOG.info("NOVA 01 renderer started (%s, %s)", system_info.kind, system_info.model)

    while not stop_event.is_set():
        if max_frames is not None and frames >= max_frames:
            break

        snapshot = metrics.snapshot()
        weather_snap = weather.snapshot()
        cpu_history.append(snapshot.cpu_percent)
        temp_val = snapshot.cpu_temp_c if snapshot.cpu_temp_c is not None else 0.0
        temp_history.append(temp_val)
        procs_history.append(snapshot.process_count)

        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)

        # ── 1. RIGHT TOP HEADER (Network Rates & WiFi Icon X=444, Y=14) ──
        up_val = format_rate(snapshot.net_up_mb_s)
        dn_val = format_rate(snapshot.net_down_mb_s)
        
        # UP Network Block
        d.text((290, 10), "UP", font=fNano, fill=TEXT_MUTED)
        draw_up_arrow(d, 276, 21, CYAN)
        d.text((286, 20), up_val, font=fMedium, fill=CYAN)
        d.text((276, 34), "MB/s", font=fNano, fill=TEXT_MUTED)

        # DOWN Network Block
        d.text((370, 10), "DOWN", font=fNano, fill=TEXT_MUTED)
        draw_down_arrow(d, 356, 21, PURPLE)
        d.text((366, 20), dn_val, font=fMedium, fill=PURPLE)
        d.text((356, 34), "MB/s", font=fNano, fill=TEXT_MUTED)

        # Top-Right Wi-Fi Signal Icon
        draw_wifi_icon(d, 440, 16, TEXT_WHITE)

        # ── 2. LEFT MAIN CONTAINER PANEL (10, 10, 248, 240) Center X = 129 ──
        d.rounded_rectangle([10, 10, 248, 240], radius=8, fill=CARD_BG, outline=CARD_BORDER, width=1)

        # Computer Icon & Mac model inside top of Left Container
        draw_computer_icon(d, 22, 18, TEXT_WHITE)
        d.text((50, 15), display_model_name(system_info), font=fTitle, fill=TEXT_WHITE)
        d.text((50, 30), system_info.os_version, font=fMicro, fill=TEXT_MUTED)

        # Centered Clock & Date with generous breathing room
        time_str = time.strftime("%H:%M")
        date_str = time.strftime("%a   %d   %b   %Y").upper()

        w_clock = d.textlength(time_str, font=fClock)
        w_date = d.textlength(date_str, font=fDate)

        # Draw Clock & Date CENTERED horizontally at X = 129
        d.text((129 - w_clock / 2, 46), time_str, font=fClock, fill=TEXT_WHITE)
        d.text((129 - w_date / 2, 104), date_str, font=fDate, fill=CYAN)

        # Horizontal separator line 1 under Date line
        d.line([(18, 122), (240, 122)], fill=CARD_BORDER, width=1)

        # Weather Section PERFECTLY CENTERED (Icon x=34..66, Text x=74..162, Divider x=172, Stats x=180..215)
        draw_huge_weather_icon(d, 34, 130, weather_snap.condition)
        d.text((74, 126), weather_snap.location or "--", font=fNano, fill=TEXT_MUTED)
        d.text((74, 136), weather_snap.temperature, font=fWeatherTemp, fill=TEXT_WHITE)
        d.text((74, 162), weather_snap.description, font=fMicro, fill=TEXT_MUTED)

        # Vertical separator line
        d.line([(172, 126), (172, 172)], fill=CARD_BORDER, width=1)

        # Right weather stats: Thermometers & Droplet
        draw_mini_thermometer(d, 180, 128, ORANGE)
        d.text((192, 128), weather_snap.high_c, font=fMicro, fill=ORANGE)

        draw_mini_thermometer(d, 180, 144, BLUE_TEMP)
        d.text((192, 144), weather_snap.low_c, font=fMicro, fill=BLUE_TEMP)

        draw_droplet_icon(d, 180, 160, TEXT_WHITE)
        d.text((192, 160), weather_snap.humidity, font=fMicro, fill=TEXT_WHITE)

        # Horizontal separator line 2 before 5-day forecast
        d.line([(18, 176), (240, 176)], fill=CARD_BORDER, width=1)

        # 5-Day Forecast Row (ALWAYS 5 full consecutive days: THU, FRI, SAT, SUN, MON)
        forecast = weather_snap.forecast_days
        for idx in range(5):
            col_x0 = 18 + idx * 44
            cx = col_x0 + 22

            if idx > 0:
                d.line([(col_x0, 178), (col_x0, 236)], fill=CARD_BORDER, width=1)

            if idx < len(forecast):
                day_name, day_cond, day_hi, day_lo = forecast[idx]
            else:
                day_name, day_cond, day_hi, day_lo = ("SUN", "clear", "34°", "27°")

            w_dn = d.textlength(day_name, font=fNano)
            d.text((cx - w_dn / 2, 180), day_name, font=fNano, fill=TEXT_MUTED)

            draw_weather_icon(d, int(cx - 10), 194, day_cond, scale=0.9)

            range_str = f"{day_hi}/{day_lo}"
            w_rs = d.textlength(range_str, font=fNano)
            d.text((cx - w_rs / 2, 220), range_str, font=fNano, fill=TEXT_WHITE)

        # ── 3. RIGHT COLUMN CARDS (258, 48, 470, 240) ──
        # CPU Card (258, 48, 470, 108)
        d.rounded_rectangle([258, 48, 470, 108], radius=6, fill=CARD_BG, outline=CARD_BORDER, width=1)
        cpu_p = snapshot.cpu_percent
        draw_arc_gauge(d, (266, 56, 306, 96), cpu_p, CYAN)
        w_p = d.textlength(f"{cpu_p:.0f}%", font=fNano)
        d.text((286 - w_p / 2, 71), f"{cpu_p:.0f}%", font=fNano, fill=TEXT_WHITE)

        d.text((316, 54), "CPU", font=fMedium, fill=TEXT_WHITE)
        draw_glowing_wave_graph(d, (316, 68, 460, 86), cpu_history, CYAN)
        freq_str = f"{snapshot.cpu_frequency_ghz:.1f} GHz" if snapshot.cpu_frequency_ghz else "N/A"
        d.text((316, 90), freq_str, font=fNano, fill=TEXT_MUTED)
        d.text((430, 90), "60 sec", font=fNano, fill=TEXT_MUTED)

        # RAM Card (258, 114, 470, 174)
        d.rounded_rectangle([258, 114, 470, 174], radius=6, fill=CARD_BG, outline=CARD_BORDER, width=1)
        ram_p = snapshot.ram_percent
        draw_arc_gauge(d, (266, 122, 306, 162), ram_p, PURPLE)
        w_rp = d.textlength(f"{ram_p:.0f}%", font=fNano)
        d.text((286 - w_rp / 2, 137), f"{ram_p:.0f}%", font=fNano, fill=TEXT_WHITE)

        d.text((316, 120), "RAM", font=fMedium, fill=TEXT_WHITE)
        draw_segment_bar(d, (316, 138, 460, 150), ram_p, PURPLE)
        ram_str = f"{snapshot.ram_used_gb:.1f} / {snapshot.ram_total_gb:.0f} GB"
        d.text((385, 156), ram_str, font=fNano, fill=TEXT_MUTED)

        # SSD Card (258, 180, 470, 240)
        d.rounded_rectangle([258, 180, 470, 240], radius=6, fill=CARD_BG, outline=CARD_BORDER, width=1)
        ssd_p = snapshot.disk_percent
        draw_arc_gauge(d, (266, 188, 306, 228), ssd_p, BLUE)
        w_sp = d.textlength(f"{ssd_p:.0f}%", font=fNano)
        d.text((286 - w_sp / 2, 203), f"{ssd_p:.0f}%", font=fNano, fill=TEXT_WHITE)

        d.text((316, 186), "SSD", font=fMedium, fill=TEXT_WHITE)
        draw_segment_bar(d, (316, 204, 460, 216), ssd_p, BLUE)
        ssd_str = f"{snapshot.disk_used_gb:.0f} / {snapshot.disk_total_gb:.0f} GB"
        d.text((385, 222), ssd_str, font=fNano, fill=TEXT_MUTED)

        # ── 4. BOTTOM UTILITY BAR (4 Cards Across, Y=246..310) ──
        # Card 1: FAN
        d.rounded_rectangle([10, 246, 120, 310], radius=6, fill=CARD_BG, outline=CARD_BORDER, width=1)
        draw_fan_icon(d, 16, 256, TEXT_MUTED)
        d.text((46, 249), "FAN", font=fNano, fill=TEXT_MUTED)
        fan_rpm = snapshot.fan_rpm
        fan_str = "0 RPM" if fan_rpm is None or fan_rpm == 0 else f"{fan_rpm} RPM"
        d.text((46, 260), fan_str, font=fTitle, fill=TEXT_WHITE)
        fan_st = "SILENT" if fan_rpm is None or fan_rpm == 0 else "ACTIVE"
        d.text((46, 276), fan_st, font=fNano, fill=TEXT_MUTED)
        draw_segment_bar(d, (46, 290, 110, 296), 20 if fan_st == "SILENT" else 80, CYAN)

        # Card 2: TEMP
        d.rounded_rectangle([126, 246, 236, 310], radius=6, fill=CARD_BG, outline=CARD_BORDER, width=1)
        draw_thermometer_icon(d, 134, 256, ORANGE)
        d.text((156, 249), "TEMP", font=fNano, fill=TEXT_MUTED)
        t_val_str = f"{temp_val:.0f}°C"
        d.text((156, 260), t_val_str, font=fTitle, fill=TEXT_WHITE)
        draw_glowing_wave_graph(d, (134, 290, 228, 304), temp_history, ORANGE)

        # Card 3: UPTIME
        d.rounded_rectangle([242, 246, 352, 310], radius=6, fill=CARD_BG, outline=CARD_BORDER, width=1)
        draw_clock_icon(d, 250, 256, CYAN)
        d.text((276, 249), "UPTIME", font=fNano, fill=TEXT_MUTED)
        up_str = format_uptime(snapshot.uptime_seconds)
        d.text((276, 262), up_str, font=fMicro, fill=TEXT_WHITE)
        uptime_history.append(float(snapshot.uptime_seconds % 3600))
        draw_glowing_wave_graph(d, (250, 290, 344, 304), uptime_history, CYAN)

        # Card 4: PROCESSES
        d.rounded_rectangle([358, 246, 470, 310], radius=6, fill=CARD_BG, outline=CARD_BORDER, width=1)
        draw_pulse_icon(d, 366, 256, TEXT_WHITE)
        d.text((394, 249), "PROCESSES", font=fNano, fill=TEXT_MUTED)
        d.text((394, 260), str(snapshot.process_count), font=fTitle, fill=TEXT_WHITE)
        d.text((394, 276), "Running", font=fNano, fill=TEXT_MUTED)
        draw_glowing_wave_graph(d, (366, 290, 462, 304), procs_history, PURPLE)

        # Send frame to hardware
        send_full_frame(transport, img, config.device.chunk_size)
        frames += 1
        stop_event.wait(config.display.stats_interval)
