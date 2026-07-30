from __future__ import annotations

from PIL import Image

CLEAR = 102
SCREEN_OFF = 108
SCREEN_ON = 109
SET_BRIGHTNESS = 110
SET_ORIENTATION = 121
DISPLAY_BITMAP = 197


def build_command(command: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> bytes:
    return bytes((
        x >> 2,
        ((x & 3) << 6) + (y >> 4),
        ((y & 15) << 4) + (ex >> 6),
        ((ex & 63) << 2) + (ey >> 8),
        ey & 255,
        command,
    ))


def orientation_command(width: int, height: int, orientation: int = 3) -> bytes:
    payload = bytearray(16)
    payload[5] = SET_ORIENTATION
    payload[6] = orientation + 100
    payload[7] = width >> 8
    payload[8] = width & 255
    payload[9] = height >> 8
    payload[10] = height & 255
    return bytes(payload)


def image_to_rgb565le(image: Image.Image) -> bytes:
    rgb = image.convert("RGB").tobytes()
    output = bytearray((len(rgb) // 3) * 2)
    out_index = 0
    for index in range(0, len(rgb), 3):
        red, green, blue = rgb[index:index + 3]
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        output[out_index] = value & 0xFF
        output[out_index + 1] = value >> 8
        out_index += 2
    return bytes(output)
