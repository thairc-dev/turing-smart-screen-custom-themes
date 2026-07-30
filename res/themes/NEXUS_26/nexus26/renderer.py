import time
import math
import logging
from PIL import Image, ImageDraw, ImageFont

from .config import AppConfig
from .metrics import MetricsCollector, SystemInfo, display_model_name
from .protocol import CLEAR, DISPLAY_BITMAP, SCREEN_OFF, SCREEN_ON, SET_BRIGHTNESS, build_command, image_to_rgb565le, orientation_command
from .transports.base import DisplayTransport
from .weather import WeatherCollector

W, H = 480, 320
LOG = logging.getLogger(__name__)

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


def send_partial_update(
    transport: DisplayTransport,
    crop_img: Image.Image,
    box: tuple[int, int, int, int],
    chunk_size: int,
) -> None:
    x0, y0, x1, y1 = box
    transport.write(build_command(DISPLAY_BITMAP, x0, y0, x1, y1), timeout_ms=500)
    write_stream(transport, image_to_rgb565le(crop_img), chunk_size)


def cleanse_display(transport, chunk_size):
    black = Image.new("RGB", (W, H), (0, 0, 0))
    transport.write(build_command(SCREEN_OFF))
    time.sleep(0.05)
    transport.write(orientation_command(320, 480, orientation=0))
    time.sleep(0.05)
    transport.write(build_command(CLEAR))
    time.sleep(0.50)
    transport.write(orientation_command(W, H, orientation=3))
    time.sleep(0.10)
    transport.write(build_command(DISPLAY_BITMAP, 0, 0, W - 1, H - 1), timeout_ms=1000)
    write_stream(transport, image_to_rgb565le(black), chunk_size, timeout_ms=2000)
    time.sleep(0.025)

# 🌊 BEAUTIFUL SMOOTH FILLED-GRADIENT WAVE GRAPH (MATCHING CPU/GPU CONCEPT 100%)
def draw_concept_smooth_wave_graph(draw, box, history, line_color=(192, 132, 252), fill_color=(50, 20, 85)):
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    
    if len(history) < 2:
        return

    num_raw = len(history)
    smooth_points = []
    
    steps = 45 # High density interpolation
    for i in range(steps):
        t = i / (steps - 1)
        idx_f = t * (num_raw - 1)
        idx0 = int(idx_f)
        idx1 = min(num_raw - 1, idx0 + 1)
        frac = idx_f - idx0
        
        val = history[idx0] * (1.0 - frac) + history[idx1] * frac
        px = x0 + int(t * w)
        py = y1 - int(((val / 100.0) * (h - 6))) - 3
        py = max(y0 + 2, min(y1 - 1, py))
        smooth_points.append((px, py))

    poly_pts = [(x0, y1)] + smooth_points + [(x1, y1)]
    draw.polygon(poly_pts, fill=fill_color)
    draw.line(smooth_points, fill=line_color, width=2)

# 💊 BEAUTIFUL RGB CAPSULE ROUNDED PILL PROGRESS BAR (MATCHING RAM/SSD CONCEPT 100%)
def draw_concept_rgb_pill_bar(draw, box, percent):
    x0, y0, x1, y1 = box
    h = y1 - y0
    radius = h // 2
    
    # Dark track capsule
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=(18, 20, 40), outline=(32, 36, 68), width=1)
    
    w = (x1 - 2) - (x0 + 2)
    if percent > 0 and w > 0:
        fill_w = max(radius * 2, int(w * (percent / 100.0)))
        fill_x1 = min(x1 - 2, x0 + 2 + fill_w)
        
        # Draw base glowing gradient capsule (Purple #a855f7)
        draw.rounded_rectangle([x0 + 2, y0 + 2, fill_x1, y1 - 2], radius=radius-1, fill=(168, 85, 247))
        
        # Overlay bright leading edge highlight (Cyber Lilac #c084fc)
        if fill_x1 - (x0 + 2) > 10:
            highlight_x0 = max(x0 + 2, fill_x1 - 14)
            draw.rounded_rectangle([highlight_x0, y0 + 2, fill_x1, y1 - 2], radius=radius-1, fill=(192, 132, 252))

def draw_centered_text(draw, cx, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)

def draw_cpu_icon(draw, x, y, color=(168, 85, 247)):
    draw.rectangle([x+2, y+2, x+16, y+16], outline=color, fill=(20, 24, 45), width=1)
    draw.rectangle([x+6, y+6, x+12, y+12], fill=color)
    for p in [x+5, x+9, x+13]:
        draw.line([(p, y), (p, y+1)], fill=color)
        draw.line([(p, y+17), (p, y+18)], fill=color)
    for p in [y+5, y+9, y+13]:
        draw.line([(x, p), (x+1, p)], fill=color)
        draw.line([(x+17, p), (x+18, p)], fill=color)

def draw_gpu_icon(draw, x, y, color=(168, 85, 247)):
    draw.rectangle([x+1, y+3, x+17, y+15], outline=color, fill=(20, 24, 45), width=1)
    draw.ellipse([x+3, y+5, x+8, y+10], outline=color)
    draw.ellipse([x+8, y+5, x+13, y+10], outline=color)

def draw_ram_icon(draw, x, y, color=(168, 85, 247)):
    draw.rectangle([x+1, y+3, x+17, y+15], outline=color, fill=(20, 24, 45), width=1)
    for cx in [x+4, x+8, x+12, x+15]:
        draw.rectangle([cx, y+6, cx+1, y+12], fill=color)

def draw_ssd_icon(draw, x, y, color=(168, 85, 247)):
    draw.rectangle([x+2, y+2, x+16, y+16], outline=color, fill=(20, 24, 45), width=1)
    draw.line([(x+5, y+6), (x+13, y+6)], fill=color)
    draw.ellipse([x+5, y+11, x+7, y+13], fill=color)

def draw_concept_fan_icon(draw, x, y, color=(168, 85, 247)):
    cx, cy = x + 12, y + 12
    draw.ellipse([cx-3, cy-3, cx+3, cy+3], outline=color, width=1)
    for a in [0, 90, 180, 270]:
        rad = math.radians(a)
        rad2 = math.radians(a + 45)
        x1 = cx + 4 * math.cos(rad)
        y1 = cy + 4 * math.sin(rad)
        x2 = cx + 11 * math.cos(rad2)
        y2 = cy + 11 * math.sin(rad2)
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)

def draw_concept_network_icon(draw, x, y, color=(168, 85, 247)):
    draw.rectangle([x+9, y+1, x+15, y+7], outline=color, fill=(20, 24, 45), width=1)
    draw.rectangle([x+1, y+15, x+7, y+21], outline=color, fill=(20, 24, 45), width=1)
    draw.rectangle([x+9, y+15, x+15, y+21], outline=color, fill=(20, 24, 45), width=1)
    draw.rectangle([x+17, y+15, x+23, y+21], outline=color, fill=(20, 24, 45), width=1)
    draw.line([(x+12, y+7), (x+12, y+11)], fill=color, width=1)
    draw.line([(x+4, y+11), (x+20, y+11)], fill=color, width=1)
    draw.line([(x+4, y+11), (x+4, y+15)], fill=color, width=1)
    draw.line([(x+12, y+11), (x+12, y+15)], fill=color, width=1)
    draw.line([(x+20, y+11), (x+20, y+15)], fill=color, width=1)

def draw_concept_clock_icon(draw, x, y, color=(168, 85, 247)):
    draw.ellipse([x+1, y+1, x+23, y+23], outline=color, width=2)
    draw.line([(x+12, y+12), (x+12, y+6)], fill=color, width=2)
    draw.line([(x+12, y+12), (x+17, y+12)], fill=color, width=2)

def draw_concept_weather_icon(draw, x, y, condition="partly_cloudy"):
    sun = (250, 204, 21)
    cloud = (148, 163, 184)
    rain = (96, 165, 250)
    card_bg = (12, 13, 30)

    if condition == "fog":
        for offset in (8, 14, 20):
            draw.line([(x + 2, y + offset), (x + 26, y + offset)], fill=cloud, width=2)
        return

    if condition in {"clear", "partly_cloudy", "unknown"}:
        sun_cx = x + (13 if condition == "clear" else 19)
        sun_cy = y + (12 if condition == "clear" else 7)
        draw.ellipse(
            [sun_cx - 5, sun_cy - 5, sun_cx + 5, sun_cy + 5],
            outline=sun,
            width=2,
        )
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            ray_x0 = round(sun_cx + math.cos(radians) * 7)
            ray_y0 = round(sun_cy + math.sin(radians) * 7)
            ray_x1 = round(sun_cx + math.cos(radians) * 9)
            ray_y1 = round(sun_cy + math.sin(radians) * 9)
            draw.line([(ray_x0, ray_y0), (ray_x1, ray_y1)], fill=sun, width=2)
        if condition == "clear":
            return

    draw.ellipse([x + 1, y + 13, x + 10, y + 22], fill=card_bg)
    draw.ellipse([x + 6, y + 9, x + 20, y + 23], fill=card_bg)
    draw.ellipse([x + 16, y + 13, x + 27, y + 23], fill=card_bg)
    draw.rectangle([x + 5, y + 16, x + 23, y + 23], fill=card_bg)

    draw.arc([x + 1, y + 13, x + 10, y + 22], 90, 270, fill=cloud, width=2)
    draw.arc([x + 6, y + 9, x + 20, y + 23], 180, 326, fill=cloud, width=2)
    draw.arc([x + 16, y + 13, x + 27, y + 23], 270, 450, fill=cloud, width=2)
    draw.line([(x + 5, y + 23), (x + 22, y + 23)], fill=cloud, width=2)

    if condition == "rain":
        for offset in (7, 14, 21):
            draw.line([(x + offset, y + 25), (x + offset - 2, y + 28)], fill=rain, width=1)
    elif condition == "snow":
        for offset in (7, 14, 21):
            draw.point((x + offset, y + 27), fill=rain)
            draw.point((x + offset - 1, y + 27), fill=rain)
    elif condition == "thunder":
        draw.line([(x + 15, y + 23), (x + 11, y + 28), (x + 15, y + 27), (x + 12, y + 31)], fill=sun, width=2)

def draw_heart_icon(draw, cx, y, color=(192, 132, 252)):
    pts = [
        (cx, y + 14),
        (cx - 6, y + 8),
        (cx - 7, y + 4),
        (cx - 5, y + 1),
        (cx - 2, y + 1),
        (cx, y + 4),
        (cx + 2, y + 1),
        (cx + 5, y + 1),
        (cx + 7, y + 4),
        (cx + 6, y + 8),
        (cx, y + 14)
    ]
    draw.polygon(pts, outline=color, fill=None)

def draw_up_arrow(draw, x, y, color=(168, 85, 247)):
    draw.polygon([(x+2, y), (x, y+5), (x+4, y+5)], fill=color)

def draw_down_arrow(draw, x, y, color=(168, 85, 247)):
    draw.polygon([(x, y), (x+4, y), (x+2, y+5)], fill=color)

def draw_fan_value(draw, right_x, y, rpm, value_font, unit_font, compact_font, value_color, unit_color):
    """Draw an RPM value inside a fixed-width card and return its pixel bounds."""
    if rpm is None:
        text = "N/A"
        width = math.ceil(draw.textlength(text, font=value_font))
        left_x = right_x - width
        draw.text((left_x, y), text, fill=value_color, font=value_font)
        return left_x, right_x

    number = str(rpm) if rpm < 10_000 else f"{min(99, round(rpm / 1000))}K"
    gap = 3
    number_width = math.ceil(draw.textlength(number, font=value_font))
    unit_width = math.ceil(draw.textlength("RPM", font=unit_font))
    total_width = number_width + gap + unit_width

    # Four-digit RPM values fit when the smaller unit is baseline-aligned.
    # Keep a compact fallback for abnormal five-digit sensor values.
    if total_width <= 55:
        left_x = right_x - total_width
        draw.text((left_x, y), number, fill=value_color, font=value_font)
        draw.text(
            (left_x + number_width + gap, y + 5),
            "RPM",
            fill=unit_color,
            font=unit_font,
        )
    else:
        text = f"{number} RPM"
        width = math.ceil(draw.textlength(text, font=compact_font))
        left_x = right_x - width
        draw.text((left_x, y + 2), text, fill=value_color, font=compact_font)
    return left_x, right_x

def format_network_rate(rate_mb_s: float) -> str:
    """Keep high-throughput values inside one half of the network card."""
    rate = max(0.0, rate_mb_s)
    if rate < 100:
        return f"{rate:.1f}"
    if rate < 1000:
        return f"{rate:.0f}"
    return f"{min(99.9, rate / 1000):.1f}K"


def format_uptime(uptime_seconds: int) -> tuple[str, str]:
    """Return two compact uptime lines that remain safe on long-lived hosts."""
    seconds = max(0, uptime_seconds)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days >= 1000:
        return f"{days / 365.25:.1f}y", f"{hours}h {minutes}m"
    return f"{days}d {hours}h", f"{minutes}m"

# 🎵 28-COLUMN WIDE CENTER DOT MATRIX AUDIO VISUALIZER
def draw_wide_center_dot_matrix_visualizer(draw, x_start, y_base, m_time, per_core, color=(168, 85, 247)):
    del m_time
    num_cols = 28
    core_levels = [max(0.0, min(100.0, float(value))) for value in (per_core or [0.0])]

    for col_idx in range(num_cols):
        col_x = x_start + col_idx * 4

        # Stretch the available CPU cores across the header once. Repeating
        # them with modulo made the graph look like three equalizers joined.
        if len(core_levels) == 1:
            core_val = core_levels[0]
        else:
            source_pos = col_idx * (len(core_levels) - 1) / (num_cols - 1)
            left_idx = int(source_pos)
            right_idx = min(left_idx + 1, len(core_levels) - 1)
            blend = source_pos - left_idx
            core_val = (
                core_levels[left_idx] * (1.0 - blend)
                + core_levels[right_idx] * blend
            )
        load_factor = max(0.0, min(1.0, core_val / 100.0))
        dots_count = max(1, min(8, int(load_factor * 8.0) + 1))
        
        for dot_i in range(dots_count):
            dot_y = y_base - dot_i * 3
            dot_color = (255, 255, 255) if dot_i == dots_count - 1 and dots_count > 3 else color
            draw.ellipse([col_x - 1, dot_y - 1, col_x + 1, dot_y + 1], fill=dot_color)

# 🌌 Siri / M4 Quantum Breathing Pulse Core (100% Stutter-Free Harmonic Pulse!)
def draw_quantum_breathing_pulse_core(draw, cx, cy, monotonic_time, is_warning=False):
    num_dots = 48
    pulse = 0.5 + 0.5 * math.sin(monotonic_time * (2 * math.pi / 2.4))
    
    for i in range(num_dots):
        dot_angle = i * (2 * math.pi / num_dots)
        cos_a = math.cos(dot_angle)
        sin_a = math.sin(dot_angle)
        
        is_cardinal = (i % (num_dots // 4) == 0)

        for step, r in enumerate([73, 78, 83, 88]):
            dx = int(cx + r * cos_a)
            dy = int(cy + r * sin_a)
            
            layer_pulse = pulse if step in [1, 2] else (1.0 - pulse)
            
            if is_cardinal:
                base_c = (192, 132, 252) # Cyber Lilac Accent
                glow_c = (255, 255, 255) # White Highlight
            else:
                if step == 0: base_c = (110, 55, 175)
                elif step == 1: base_c = (70, 25, 120)
                elif step == 2: base_c = (40, 10, 75)
                else: base_c = (18, 4, 40)
                
                glow_c = (168, 85, 247) # Neon Purple
                
            if is_warning:
                glow_c = (245, 158, 11)
                
            r_c = int(base_c[0] * (1.0 - layer_pulse * 0.5) + glow_c[0] * (layer_pulse * 0.5))
            g_c = int(base_c[1] * (1.0 - layer_pulse * 0.5) + glow_c[1] * (layer_pulse * 0.5))
            b_c = int(base_c[2] * (1.0 - layer_pulse * 0.5) + glow_c[2] * (layer_pulse * 0.5))
            
            draw.ellipse([dx - 1, dy - 1, dx + 1, dy + 1], fill=(r_c, g_c, b_c))

def create_clean_base_bg():
    bg = Image.new("RGB", (W, H), (7, 7, 20)) # Deep Dark Navy #070714
    d = ImageDraw.Draw(bg)
    # Left Card Container (Y=44..238)
    d.rounded_rectangle([12, 44, 240, 238], radius=8, fill=(12, 13, 30), outline=(25, 27, 55), width=1)
    d.line([(12, 44), (12, 238)], fill=(120, 60, 220), width=1)
    for y_joint in [44, 92, 140, 188, 238]:
        d.ellipse([10, y_joint - 2, 14, y_joint + 2], fill=(168, 85, 247))
    d.line([(14, 92), (238, 92)], fill=(25, 27, 55), width=1)
    d.line([(14, 140), (238, 140)], fill=(25, 27, 55), width=1)
    d.line([(14, 188), (238, 188)], fill=(25, 27, 55), width=1)

    # Bottom utility bar. The network card intentionally gets more width, as
    # it carries two values; this matches the airier concept proportions.
    d.rounded_rectangle([12, 244, 468, 312], radius=8, fill=(12, 13, 30), outline=(25, 27, 55), width=1)
    for div_x in [108, 252, 356]:
        d.line([(div_x, 255), (div_x, 301)], fill=(27, 30, 58), width=1)
    return bg

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
        cleanse_display(
            transport,
            config.device.chunk_size,
        )
    transport.write(build_command(SCREEN_ON))
    brightness_value = int(255 - config.display.brightness * 2.55)
    transport.write(build_command(SET_BRIGHTNESS, brightness_value, 0, 0, 0))
    transport.write(orientation_command(W, H))
    time.sleep(0.2)

    base_bg = create_clean_base_bg()
    apple_logo = Image.open(config.assets_dir / "apple_logo_large.png").convert("RGBA")
    windows_logo = Image.open(config.assets_dir / "windows_logo.png").convert("RGBA")

    bold_font = config.fonts_dir / "Roboto-Bold.ttf"
    regular_font = config.fonts_dir / "Roboto-Regular.ttf"
    try:
        fTitle = ImageFont.truetype(str(bold_font), 18)
        fHeaderTime = ImageFont.truetype(str(bold_font), 30)
        fBigVal = ImageFont.truetype(str(bold_font), 24)
        fCardVal = ImageFont.truetype(str(bold_font), 14)
        fSystemGood = ImageFont.truetype(str(bold_font), 32)
        fMedium = ImageFont.truetype(str(bold_font), 12)
        fSmall = ImageFont.truetype(str(regular_font), 11)
        fMicro = ImageFont.truetype(str(bold_font), 10)
        fNano = ImageFont.truetype(str(regular_font), 9)
    except OSError as exc:
        LOG.warning("Could not load bundled fonts: %s", exc)
        fTitle = fHeaderTime = fBigVal = fCardVal = fSystemGood = fMedium = fSmall = fMicro = fNano = ImageFont.load_default()

    WHITE = (255, 255, 255)
    PURPLE_NEON = (168, 85, 247)
    PURPLE_LIGHT = (192, 132, 252)
    GRAY_TEXT = (148, 163, 184)
    AMBER_WARN = (245, 158, 11)

    os_type = system_info.kind
    real_model = display_model_name(system_info)
    real_os = system_info.os_version
    os_logo_img = apple_logo if os_type == "apple" else windows_logo

    initial_snapshot = metrics.snapshot()
    cpu_history = [initial_snapshot.cpu_percent] * 24
    initial_gpu = initial_snapshot.gpu_percent or 0.0
    gpu_history = [initial_gpu] * 24
    cpu_history_initialized = initial_snapshot.cpu_percent > 0
    gpu_history_initialized = initial_snapshot.gpu_percent is not None

    # 🍎 PROMINENT LARGE APPLE LOGO (34x34px) AT X=12, Y=4
    init_img = base_bg.copy()
    init_d = ImageDraw.Draw(init_img)
    init_img.paste(os_logo_img, (12, 4), os_logo_img)
    init_d.text((50, 6), real_model, fill=WHITE, font=fTitle)
    init_d.text((50, 26), real_os, fill=GRAY_TEXT, font=fSmall)
    
    transport.write(build_command(DISPLAY_BITMAP, 0, 0, 479, 319), timeout_ms=1000)
    write_stream(
        transport,
        image_to_rgb565le(init_img),
        config.device.chunk_size,
        timeout_ms=2000,
    )
    time.sleep(0.1)

    ring_base_crop = base_bg.crop((268, 50, 453, 235))



    LOG.info("NEXUS 26 renderer started (%s, %s)", os_type, real_model)

    last_stats_tick = 0
    stats_step = 0
    target_frame_time = 1.0 / config.display.fps
    next_frame_time = time.monotonic()

    sys_status = "GOOD"
    sys_sub1 = "All systems"
    sys_sub2 = "operational"
    sys_color = PURPLE_LIGHT

    # Update only the equalizer crop at the main frame rate. The surrounding
    # header (logo, clock and date) can keep its slower stats refresh cadence.
    header_measure = ImageDraw.Draw(base_bg)
    viz_width = 28 * 4
    viz_left_edge = 50 + int(header_measure.textlength(real_model, font=fTitle)) + 8
    viz_right_edge = int(468 - header_measure.textlength("00:00", font=fHeaderTime)) - 8
    viz_x_start = ((viz_left_edge + viz_right_edge) // 2) - (viz_width // 2)
    viz_x0, viz_y0 = viz_x_start - 2, 7
    viz_x1, viz_y1 = viz_x_start + viz_width, 32
    header_viz_base = base_bg.crop((viz_x0, viz_y0, viz_x1 + 1, viz_y1 + 1))
    smooth_per_core = [0.0] * max(1, len(initial_snapshot.per_core))
    frame_count = 0

    while not stop_event.is_set():
        if max_frames is not None and frame_count >= max_frames:
            break
        frame_count += 1
        m_now = time.monotonic()

        # Fresh copy from base bg (exact color match, no ghost)
        ring_img = ring_base_crop.copy()
        rd = ImageDraw.Draw(ring_img)
        rcx, rcy = 360 - 268, 142 - 50

        snapshot = metrics.snapshot()
        cpu = int(snapshot.cpu_percent)
        per_core = snapshot.per_core or (0.0,)
        is_warn = snapshot.warning

        if len(smooth_per_core) != max(1, len(per_core)):
            smooth_per_core = [float(v) for v in (per_core or [30])]
        else:
            targets = per_core or [30]
            for idx, target in enumerate(targets):
                smooth_per_core[idx] += (float(target) - smooth_per_core[idx]) * 0.18
        
        sys_status = snapshot.health_status
        sys_sub1 = snapshot.health_line1
        sys_sub2 = snapshot.health_line2
        sys_color = AMBER_WARN if is_warn else PURPLE_LIGHT

        draw_quantum_breathing_pulse_core(rd, rcx, rcy, m_now, is_warning=is_warn)

        # ── Vertically centered text block inside ring (inner radius=73, center rcy=92) ──
        # Block: SYSTEM(10) + gap(3) + status(34) + gap(6) + sub1(10) + sub2(10) + gap(4) + heart(16) ≈ 93px
        # Start y = 92 - 93/2 = 45, so content spans y=45..138, center=(45+138)/2=91.5 ≈ 92 ✓
        draw_centered_text(rd, rcx, 33, "SYSTEM", fMicro, sys_color)
        # y=48 = vị trí CŨ → text mới chồng đúng lên ghost, ghost biến mất
        rd.fontmode = "1"
        status_font = fSystemGood if len(sys_status) <= 5 else fBigVal
        draw_centered_text(rd, rcx, 48, sys_status, status_font, WHITE)
        rd.fontmode = "L"
        draw_centered_text(rd, rcx, 87, sys_sub1, fMicro, GRAY_TEXT)
        draw_centered_text(rd, rcx, 98, sys_sub2, fMicro, GRAY_TEXT)
        draw_heart_icon(rd, rcx, 112, sys_color)

        send_partial_update(
            transport, ring_img, (268, 50, 452, 234), config.device.chunk_size
        )

        # Smooth 10 FPS equalizer update in a small, hub-friendly region.
        viz_img = header_viz_base.copy()
        vd = ImageDraw.Draw(viz_img)
        draw_wide_center_dot_matrix_visualizer(
            vd,
            viz_x_start - viz_x0,
            30 - viz_y0,
            m_now,
            smooth_per_core,
            PURPLE_NEON
        )
        send_partial_update(
            transport, viz_img, (viz_x0, viz_y0, viz_x1, viz_y1), config.device.chunk_size
        )

        # ── 2. INTERLEAVED STATS UPDATES (1 small box per frame interval) ──
        if m_now - last_stats_tick >= config.display.stats_interval:
            if stats_step == 0:
                # 🍎 FULL HEADER REGION COVERING (0, 0, 468, 44) WITH LARGE APPLE LOGO AT (12, 4)!
                head_img = base_bg.crop((0, 0, 469, 45)).copy()
                hd = ImageDraw.Draw(head_img)

                # 3. Right-aligned Clock & Date to screen X=468
                time_str = time.strftime("%H:%M")
                date_str = time.strftime("%a %d %b %Y").upper()

                w_time = hd.textlength(time_str, font=fHeaderTime)
                hd.text((468 - w_time, 0), time_str, fill=WHITE, font=fHeaderTime)

                w_date = hd.textlength(date_str, font=fMicro)
                hd.text((468 - w_date, 30), date_str, fill=PURPLE_NEON, font=fMicro)

                # 1. Left OS Logo & System Title
                head_img.paste(os_logo_img, (12, 4), os_logo_img)
                hd.text((50, 6), real_model, fill=WHITE, font=fTitle)
                hd.text((50, 26), real_os, fill=GRAY_TEXT, font=fSmall)

                # 2. 🎵 DYNAMICALLY CENTERED DOT MATRIX VISUALIZER
                # Compute left edge: end of right-most text between logo & model name
                left_edge = 50 + int(hd.textlength(real_model, font=fTitle)) + 8
                # Compute right edge: start of clock
                right_edge = int(468 - w_time) - 8
                draw_wide_center_dot_matrix_visualizer(
                    hd, viz_x_start, 30, m_now, smooth_per_core, PURPLE_NEON
                )

                send_partial_update(
                    transport, head_img, (0, 0, 468, 44), config.device.chunk_size
                )
                stats_step = 1

            elif stats_step == 1:
                left_img = base_bg.crop((12, 44, 241, 241)).copy()
                ld = ImageDraw.Draw(left_img)
                
                if not cpu_history_initialized and cpu > 0:
                    cpu_history = [cpu] * 24
                    cpu_history_initialized = True
                else:
                    cpu_history.append(cpu)
                    if len(cpu_history) > 24:
                        cpu_history.pop(0)

                cpu_temp = "--" if snapshot.cpu_temp_c is None else f"{snapshot.cpu_temp_c:.0f}"

                # 🎯 ROW 1: CPU (Icon, CPU Label, 31%, 52°C, Smooth Filled Wave Graph)
                draw_cpu_icon(ld, 20 - 12, 54 - 44, PURPLE_NEON)
                ld.text((46 - 12, 48 - 44), "CPU", fill=GRAY_TEXT, font=fMicro)
                ld.text((46 - 12, 60 - 44), f"{cpu}%", fill=WHITE, font=fBigVal)
                ld.text((106 - 12, 48 - 44), f"{cpu_temp}°C" if cpu_temp != "--" else "--°C", fill=PURPLE_LIGHT, font=fMedium)
                draw_concept_smooth_wave_graph(ld, [142 - 12, 52 - 44, 230 - 12, 86 - 44], cpu_history, line_color=PURPLE_LIGHT, fill_color=(50, 20, 85))

                # 🎯 ROW 2: GPU (Icon, GPU Label, 12%, 46°C, Smooth Filled Wave Graph)
                gpu = 0 if snapshot.gpu_percent is None else int(snapshot.gpu_percent)
                if not gpu_history_initialized and snapshot.gpu_percent is not None:
                    gpu_history = [gpu] * 24
                    gpu_history_initialized = True
                else:
                    gpu_history.append(gpu)
                    if len(gpu_history) > 24:
                        gpu_history.pop(0)

                gpu_temp = "--" if snapshot.gpu_temp_c is None else f"{snapshot.gpu_temp_c:.0f}"

                draw_gpu_icon(ld, 20 - 12, 102 - 44, PURPLE_NEON)
                ld.text((46 - 12, 96 - 44), "GPU", fill=GRAY_TEXT, font=fMicro)
                ld.text((46 - 12, 108 - 44), f"{gpu}%" if snapshot.gpu_percent is not None else "N/A", fill=WHITE, font=fBigVal)
                ld.text((106 - 12, 96 - 44), f"{gpu_temp}°C" if gpu_temp != "--" else "--°C", fill=PURPLE_LIGHT, font=fMedium)
                draw_concept_smooth_wave_graph(ld, [142 - 12, 100 - 44, 230 - 12, 134 - 44], gpu_history, line_color=PURPLE_LIGHT, fill_color=(50, 20, 85))

                # 🎯 ROW 3: RAM
                rp = int(snapshot.ram_percent)
                rg = snapshot.ram_used_gb
                draw_ram_icon(ld, 20 - 12, 150 - 44, PURPLE_NEON)
                ld.text((46 - 12, 144 - 44), "RAM", fill=GRAY_TEXT, font=fMicro)
                ld.text((46 - 12, 156 - 44), f"{rp}%", fill=WHITE, font=fBigVal)
                
                ram_text = f"{rg:.1f} / {snapshot.ram_total_gb:.0f} GiB"
                w_ram = ld.textlength(ram_text, font=fMedium)
                ld.text((230 - 12 - w_ram, 144 - 44), ram_text, fill=PURPLE_LIGHT, font=fMedium)
                draw_concept_rgb_pill_bar(ld, [108 - 12, 166 - 44, 230 - 12, 175 - 44], rp)

                # 🎯 ROW 4: SSD
                dp = int(snapshot.disk_percent)
                du = snapshot.disk_used_gb
                dt2 = snapshot.disk_total_gb
                draw_ssd_icon(ld, 20 - 12, 198 - 44, PURPLE_NEON)
                ld.text((46 - 12, 192 - 44), "SSD", fill=GRAY_TEXT, font=fMicro)
                ld.text((46 - 12, 204 - 44), f"{dp}%", fill=WHITE, font=fBigVal)
                
                ssd_text = f"{du:.0f} / {dt2:.0f} GB"
                w_ssd = ld.textlength(ssd_text, font=fMedium)
                ld.text((230 - 12 - w_ssd, 192 - 44), ssd_text, fill=PURPLE_LIGHT, font=fMedium)
                draw_concept_rgb_pill_bar(ld, [108 - 12, 214 - 44, 230 - 12, 223 - 44], dp)

                send_partial_update(
                    transport, left_img, (12, 44, 240, 240), config.device.chunk_size
                )
                stats_step = 2

            elif stats_step == 2:
                # 🎯 PERFECT CONCEPT-MATCHING VERTICALLY CENTERED BOTTOM BAR (Y=244..312, HEIGHT 68PX)
                bot_img = base_bg.crop((12, 244, 469, 313)).copy()
                bd = ImageDraw.Draw(bot_img)

                fan_rpm = snapshot.fan_rpm
                fan_status = "NO SENSOR" if fan_rpm is None else ("SILENT" if fan_rpm == 0 else "ACTIVE")

                # 1. FAN CARD
                draw_concept_fan_icon(bd, 22 - 12, 22, PURPLE_NEON)
                bd.text((54 - 12, 13), "FAN", fill=PURPLE_LIGHT, font=fMicro)
                fan_left, fan_right = draw_fan_value(
                    bd,
                    104 - 12,
                    27,
                    fan_rpm,
                    fCardVal,
                    fNano,
                    fMicro,
                    WHITE,
                    GRAY_TEXT,
                )
                if fan_left < 46 - 12 or fan_right > 104 - 12:
                    LOG.warning("Fan value escaped footer safe area: %s..%s", fan_left, fan_right)
                bd.text((54 - 12, 45), fan_status, fill=PURPLE_LIGHT, font=fMicro)

                # 2. NETWORK CARD
                up = snapshot.net_up_mb_s
                dn = snapshot.net_down_mb_s

                draw_concept_network_icon(bd, 120 - 12, 23, PURPLE_NEON)
                bd.text((150 - 12, 13), "NETWORK", fill=PURPLE_LIGHT, font=fMicro)

                draw_up_arrow(bd, 150 - 12, 29, PURPLE_NEON)
                bd.text((157 - 12, 26), format_network_rate(up), fill=WHITE, font=fCardVal)

                draw_down_arrow(bd, 198 - 12, 29, PURPLE_NEON)
                bd.text((205 - 12, 26), format_network_rate(dn), fill=WHITE, font=fCardVal)

                bd.text((157 - 12, 44), "MB/s", fill=GRAY_TEXT, font=fNano)
                bd.text((205 - 12, 44), "MB/s", fill=GRAY_TEXT, font=fNano)

                # 3. UPTIME CARD
                us = snapshot.uptime_seconds
                ust_h, ust_m = format_uptime(us)

                draw_concept_clock_icon(bd, 264 - 12, 22, PURPLE_NEON)
                bd.text((294 - 12, 13), "UPTIME", fill=PURPLE_LIGHT, font=fMicro)
                bd.text((294 - 12, 27), ust_h, fill=WHITE, font=fCardVal)
                bd.text((294 - 12, 45), ust_m, fill=WHITE, font=fCardVal)

                # 4. WEATHER CARD
                weather_snapshot = weather.snapshot()
                draw_concept_weather_icon(bd, 366 - 12, 22, weather_snapshot.condition)
                bd.text((398 - 12, 13), "WEATHER", fill=PURPLE_LIGHT, font=fMicro)
                bd.text((398 - 12, 27), weather_snapshot.temperature, fill=WHITE, font=fCardVal)
                bd.text((398 - 12, 45), weather_snapshot.description, fill=GRAY_TEXT, font=fNano)

                send_partial_update(
                    transport, bot_img, (12, 244, 468, 312), config.device.chunk_size
                )
                
                stats_step = 0
                last_stats_tick = m_now

        # Monotonic high-precision clock sleep compensation.
        next_frame_time += target_frame_time
        sleep_time = next_frame_time - time.monotonic()
        if sleep_time > 0:
            stop_event.wait(sleep_time)
        else:
            next_frame_time = time.monotonic()
