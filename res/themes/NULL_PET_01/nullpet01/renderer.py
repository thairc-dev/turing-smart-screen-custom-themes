from __future__ import annotations

import os
import time
import math
import logging
from PIL import Image, ImageDraw, ImageFont

LOG = logging.getLogger(__name__)

# Canvas dimensions
W, H = 480, 320

# Retro CRT Palette (Green & Cyan Phosphor)
COLOR_BG = (3, 6, 16)                # Pitch CRT Black
COLOR_PANEL = (8, 16, 32)            # CRT Terminal Fill
COLOR_PANEL_HDR = (4, 10, 22)        # CRT Terminal Header
COLOR_BORDER = (0, 200, 150)         # CRT Phosphor Border
COLOR_PHOSPHOR_GREEN = (0, 255, 102) # #00FF66 Retro CRT Green
COLOR_CYAN = (0, 229, 255)           # #00E5FF Phosphor Cyan
COLOR_AMBER = (255, 176, 0)          # #FFB000 Phosphor Amber
COLOR_RED = (255, 42, 85)             # #FF2A55 CRT Alert Red
COLOR_WHITE = (240, 248, 255)        # Retro White
COLOR_MUTED = (100, 140, 160)        # CRT Muted Text


class NullPetRenderer:
    def __init__(self, width: int = 480, height: int = 320):
        self.width = width
        self.height = height
        
        # Load spritesheet from package directory
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        self.sheet_path = os.path.join(pkg_dir, "spritesheet.webp")
        if not os.path.exists(self.sheet_path):
            self.sheet_path = "/Users/thairc/.gemini/antigravity/brain/e79ffeeb-45d6-459c-9d79-843c91013ee4/scratch/pet_spritesheet.webp"
        
        if os.path.exists(self.sheet_path):
            self.sheet = Image.open(self.sheet_path).convert("RGBA")
        else:
            self.sheet = None

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        safe_size = max(8, size)
        font_path = "/System/Library/Fonts/Menlo.ttc"
        try:
            index = 1 if bold else 0
            return ImageFont.truetype(font_path, safe_size, index=index)
        except Exception:
            try:
                return ImageFont.truetype("/System/Library/Fonts/Courier.ttc", safe_size, index=index)
            except Exception:
                return ImageFont.load_default()

    def _get_pet_sprite(self, action: str = "laptop", frame_idx: int = 0) -> Image.Image:
        if not self.sheet:
            return Image.new("RGBA", (130, 120), (0, 0, 0, 0))
        
        # Band Y offsets:
        # Band 8 (laptop coding): Y=1474
        # Band 7 (confused ? face): Y=1266
        # Band 6 (error panic): Y=1058
        band_y = 1474
        max_frames = 6

        if action == "error":
            band_y = 1058
            max_frames = 6
        elif action == "confused":
            band_y = 1266
            max_frames = 6

        x1 = (frame_idx % max_frames) * 192
        y1 = band_y
        crop = self.sheet.crop((x1, y1, x1 + 192, y1 + 180))

        # CRITICAL PIXEL ART RULE: Use NEAREST (Nearest Neighbor) sampling for sharp pixel-perfect scaling!
        # Resize to 135x125 with NEAREST filter so every pixel block stays sharp and non-blurry!
        scaled_sprite = crop.resize((135, 125), Image.Resampling.NEAREST)
        return scaled_sprite

    def _draw_crt_card(self, draw: ImageDraw.ImageDraw, box: list[int], header_title: str = ""):
        x1, y1, x2, y2 = box
        draw.rectangle([x1, y1, x2, y2], fill=COLOR_PANEL, outline=COLOR_BORDER, width=1)
        draw.rectangle([x1 + 2, y1 + 2, x2 - 2, y2 - 2], outline=(12, 28, 48), width=1)
        
        if header_title:
            draw.rectangle([x1 + 3, y1 + 3, x2 - 3, y1 + 19], fill=COLOR_PANEL_HDR)
            draw.line([x1 + 3, y1 + 19, x2 - 3, y1 + 19], fill=COLOR_BORDER, width=1)
            draw.text((x1 + 8, y1 + 5), f"> {header_title}", font=self._get_font(8, bold=True), fill=COLOR_PHOSPHOR_GREEN)

    def _draw_thought_bubble_extra_low(self, draw: ImageDraw.ImageDraw, text: str, mode: str = "normal"):
        # Cloud Bubble box starts at Y=66 (Generous 16px gap below header strip Y=50)
        bx1, by1, bx2, by2 = 20, 66, 200, 86
        
        if mode == "alert":
            bg_color = (40, 8, 16)
            border_color = COLOR_RED
        elif mode == "warning":
            bg_color = (35, 25, 8)
            border_color = COLOR_AMBER
        else:
            bg_color = (6, 22, 38)
            border_color = COLOR_CYAN

        # Cloud Box
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=8, fill=bg_color, outline=border_color, width=1)
        
        # 3 DIAGONAL Thought Circles slanting from bottom-right of cloud (X=140, Y=88) down to pet head (X=108, Y=110)
        draw.ellipse([134, 88, 142, 96], fill=bg_color, outline=border_color, width=1)
        draw.ellipse([120, 98, 126, 104], fill=bg_color, outline=border_color, width=1)
        draw.ellipse([107, 106, 111, 110], fill=bg_color, outline=border_color, width=1)

        # Thought Text inside Cloud
        draw.text((28, 71), f"💭 {text}", font=self._get_font(8), fill=COLOR_WHITE)

    def render(
        self,
        frame_idx: int = 0,
        cpu_pct: float = 34.0,
        ram_pct: float = 52.0,
        temp_c: float = 46.0,
        gpu_pct: float = 18.5,
        fan_rpm: int = 1450,
        power_w: float = 14.2,
        time_str: str = "13:19:24",
        date_str: str = "THU 06 AUG"
    ) -> Image.Image:
        img = Image.new("RGB", (self.width, self.height), COLOR_BG)
        draw = ImageDraw.Draw(img)

        # 1. Retro CRT Horizontal Scanlines
        for y in range(0, H, 2):
            draw.line([0, y, W, y], fill=(2, 4, 10), width=1)

        # Fonts
        f_micro = self._get_font(8)
        f_val = self._get_font(14, bold=True)
        f_large = self._get_font(17, bold=True)
        f_huge = self._get_font(20, bold=True)

        # Determine System State & Pet Expression
        is_alert = cpu_pct >= 80 or temp_c >= 75
        is_warning = (cpu_pct >= 65 or ram_pct >= 75) and not is_alert

        if is_alert:
            pet_action = "error"
            pet_mode = "alert"
            thought_text = "ERR: OVERHEAT!"
            status_text = "[OVERLOAD]"
            status_color = COLOR_RED
            pet_status_lbl = "> STATUS: PANIC OVERHEAT"
        elif is_warning:
            pet_action = "confused"
            pet_mode = "warning"
            thought_text = "Refactoring RAM..."
            status_text = "[HIGH LOAD]"
            status_color = COLOR_AMBER
            pet_status_lbl = "> STATUS: HIGH MEMORY"
        else:
            pet_action = "laptop"
            pet_mode = "normal"
            thought_text = "Coding & Optimizing..."
            status_text = "[OPTIMAL]"
            status_color = COLOR_PHOSPHOR_GREEN
            pet_status_lbl = "> STATUS: HAPPY CODING"

        # -------------------------------------------------------------
        # TOP HEADER: CRT TERMINAL HEADER
        # -------------------------------------------------------------
        draw.text((10, 6), "CRT::NULL-SIGNAL", font=self._get_font(11, bold=True), fill=COLOR_PHOSPHOR_GREEN)
        draw.text((150, 7), "[TERMINAL MONITOR v1.0]", font=f_micro, fill=COLOR_CYAN)

        draw.text((310, 7), status_text, font=self._get_font(9, bold=True), fill=status_color)
        draw.text((395, 6), time_str, font=f_val, fill=COLOR_WHITE)
        draw.line([10, 26, 470, 26], fill=COLOR_BORDER, width=1)

        # -------------------------------------------------------------
        # LEFT SIDE: ENLARGED PET STAGE (X=10, Y=32, W=200, H=280)
        # -------------------------------------------------------------
        self._draw_crt_card(draw, [10, 32, 210, 312], "COMPANION_STAGE")

        # Draw Diagonal Comic Thought Trail at Y=66..110
        self._draw_thought_bubble_extra_low(draw, thought_text, mode=pet_mode)

        # Crisp Pixel Art Pet Sprite centered cleanly at X=110 (Y=115 to 242)
        pet_sprite = self._get_pet_sprite(pet_action, frame_idx=frame_idx)
        
        pw, ph = pet_sprite.size
        px = 10 + (200 - pw) // 2
        py = 115 + (165 - ph) // 2
        img.paste(pet_sprite, (px, py), pet_sprite)

        # Clean Bottom Status Pill inside Pet Stage (Y=285..305)
        draw.rectangle([20, 285, 200, 305], fill=(4, 10, 20), outline=COLOR_BORDER, width=1)
        draw.text((26, 290), pet_status_lbl, font=f_micro, fill=status_color)

        # -------------------------------------------------------------
        # RIGHT SIDE: METRICS CARDS
        # -------------------------------------------------------------
        self._draw_crt_card(draw, [218, 32, 470, 120], "CPU_TELEMETRY")
        draw.text((228, 54), "CPU LOAD", font=f_micro, fill=COLOR_MUTED)
        draw.text((228, 68), f"{cpu_pct:.1f}%", font=f_huge, fill=COLOR_PHOSPHOR_GREEN)
        
        draw.rectangle([320, 72, 458, 86], fill=(4, 12, 24), outline=COLOR_BORDER, width=1)
        bar_w = int((cpu_pct / 100.0) * 134)
        if bar_w > 0:
            draw.rectangle([322, 74, 322 + bar_w, 84], fill=COLOR_PHOSPHOR_GREEN if cpu_pct < 80 else COLOR_RED)

        draw.text((228, 98), f"TEMP: {temp_c:.1f}°C", font=f_micro, fill=COLOR_MUTED)
        draw.text((370, 98), "FREQ: 3.80GHz", font=f_micro, fill=COLOR_CYAN)

        self._draw_crt_card(draw, [218, 126, 470, 214], "RAM_BUFFER")
        draw.text((228, 148), "RAM USED", font=f_micro, fill=COLOR_MUTED)
        draw.text((228, 162), f"{ram_pct:.1f}%", font=f_huge, fill=COLOR_CYAN)

        draw.rectangle([320, 166, 458, 180], fill=(4, 12, 24), outline=COLOR_BORDER, width=1)
        ram_bar_w = int((ram_pct / 100.0) * 134)
        if ram_bar_w > 0:
            draw.rectangle([322, 168, 322 + ram_bar_w, 178], fill=COLOR_CYAN)

        draw.text((228, 192), f"MEM: {(ram_pct * 0.16):.1f}GB / 16.0GB", font=f_micro, fill=COLOR_MUTED)
        draw.text((370, 192), "TYPE: DDR5", font=f_micro, fill=COLOR_PHOSPHOR_GREEN)

        self._draw_crt_card(draw, [218, 220, 470, 312], "HARDWARE_STATUS")
        
        draw.text((228, 242), "GPU", font=f_micro, fill=COLOR_MUTED)
        draw.text((228, 256), f"{gpu_pct:.1f}%", font=f_large, fill=COLOR_WHITE)

        draw.text((310, 242), "FAN", font=f_micro, fill=COLOR_MUTED)
        draw.text((310, 256), f"{fan_rpm}RPM", font=f_large, fill=COLOR_CYAN)

        draw.text((400, 242), "PWR", font=f_micro, fill=COLOR_MUTED)
        draw.text((400, 256), f"{power_w:.1f}W", font=f_large, fill=COLOR_PHOSPHOR_GREEN)

        draw.line([226, 280, 462, 280], fill=COLOR_BORDER, width=1)
        draw.text((228, 288), "STORAGE: 245GB FREE", font=f_micro, fill=COLOR_MUTED)
        draw.text((390, 288), "NET: 12.4MB/s", font=f_micro, fill=COLOR_AMBER)

        return img
