from __future__ import annotations

import os
import sys
import time
import datetime
import argparse
import psutil
from PIL import Image

import usb.core
import usb.util

from .renderer import NullPetRenderer

DISPLAY_BITMAP = 197
CLEAR = 102
SCREEN_OFF = 108
SCREEN_ON = 109
SET_ORIENTATION = 121
W, H = 480, 320


def build_command(command: int, x: int = 0, y: int = 0, ex: int = 479, ey: int = 319) -> bytes:
    return bytes((
        x >> 2,
        ((x & 3) << 6) + (y >> 4),
        ((y & 15) << 4) + (ex >> 6),
        ((ex & 63) << 2) + (ey >> 8),
        ey & 255,
        command,
    ))


def orientation_command(width: int = 480, height: int = 320, orientation: int = 3) -> bytes:
    payload = bytearray(16)
    payload[5] = SET_ORIENTATION
    payload[6] = orientation + 100
    payload[7] = width >> 8
    payload[8] = width & 255
    payload[9] = height >> 8
    payload[10] = height & 255
    return bytes(payload)


def crop_to_rgb565le(image: Image.Image, box: tuple[int, int, int, int]) -> bytes:
    crop_img = image.crop(box)
    rgb = crop_img.convert("RGB").tobytes()
    output = bytearray((len(rgb) // 3) * 2)
    out_index = 0
    for index in range(0, len(rgb), 3):
        red, green, blue = rgb[index:index + 3]
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        output[out_index] = value & 0xFF
        output[out_index + 1] = value >> 8
        out_index += 2
    return bytes(output)


def main():
    parser = argparse.ArgumentParser(description="NULL_PET_01 Theme Daemon (Unclipped Stage Patches)")
    parser.add_argument("--config", help="Path to config file", default="")
    args = parser.parse_args()

    renderer = NullPetRenderer()

    # Find USB device (TURZX 3.5")
    devices = list(usb.core.find(find_all=True, idVendor=0x1A86, idProduct=0x5722) or [])
    if not devices:
        print("TURZX 3.5 display not found via USB!")
        sys.exit(1)

    dev = devices[0]
    try:
        dev.set_configuration()
    except Exception:
        pass

    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except Exception:
        pass

    try:
        usb.util.claim_interface(dev, 0)
    except Exception:
        pass

    endpoint_addr = 0x03
    try:
        dev.clear_halt(endpoint_addr)
    except Exception:
        pass

    def send_cmd(cmd_bytes: bytes):
        try:
            dev.write(endpoint_addr, cmd_bytes, timeout=1000)
        except Exception:
            try:
                dev.clear_halt(endpoint_addr)
                dev.write(endpoint_addr, cmd_bytes, timeout=1000)
            except Exception:
                pass

    def send_rect_patch(x1: int, y1: int, x2: int, y2: int, payload: bytes):
        send_cmd(build_command(DISPLAY_BITMAP, x1, y1, x2, y2))
        chunk_size = 512
        for offset in range(0, len(payload), chunk_size):
            chunk = payload[offset:offset + chunk_size]
            try:
                dev.write(endpoint_addr, chunk, timeout=1000)
            except Exception:
                try:
                    dev.clear_halt(endpoint_addr)
                    dev.write(endpoint_addr, chunk, timeout=1000)
                except Exception:
                    pass

    # Hardware orientation reset
    send_cmd(build_command(SCREEN_OFF))
    time.sleep(0.05)
    send_cmd(orientation_command(320, 480, orientation=0))
    time.sleep(0.05)
    send_cmd(build_command(CLEAR))
    time.sleep(0.50)
    send_cmd(orientation_command(W, H, orientation=3))
    time.sleep(0.05)
    send_cmd(build_command(SCREEN_ON))
    time.sleep(0.05)

    # 1. SEND FULL FRAME ONCE AT STARTUP TO DRAW BASE STATIC CANVAS
    now = datetime.datetime.now()
    initial_img = renderer.render(
        frame_idx=0,
        cpu_pct=psutil.cpu_percent(interval=None),
        ram_pct=psutil.virtual_memory().percent,
        temp_c=46.0,
        time_str=now.strftime("%H:%M:%S")
    )
    full_payload = crop_to_rgb565le(initial_img, (0, 0, W, H))
    send_rect_patch(0, 0, W - 1, H - 1, full_payload)
    time.sleep(0.5)

    print("NULL_PET_01 unclipped patch daemon started live on TURZX 3.5 display...")

    frame_idx = 0

    # Defined UNCLIPPED Stage Bounding Box (X=12 to 208, Y=34 to 310) -> Covers Pet, Feet, Thought Cloud, and Status Pill!
    stage_box = (12, 34, 208, 310)
    clock_box = (305, 4, 470, 24)
    cpu_box = (225, 48, 465, 118)
    ram_box = (225, 142, 465, 212)

    while True:
        try:
            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M:%S")

            cpu_pct = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            temp_c = 42.0 + (cpu_pct * 0.4)

            full_frame_img = renderer.render(
                frame_idx=frame_idx,
                cpu_pct=cpu_pct,
                ram_pct=ram.percent,
                temp_c=temp_c,
                gpu_pct=15.0 + (cpu_pct * 0.2),
                fan_rpm=1200 + int(cpu_pct * 10),
                power_w=12.0 + (cpu_pct * 0.1),
                time_str=time_str
            )

            # PATCH 1: UNCLIPPED Pet Stage (X=12..208, Y=34..310)
            stage_payload = crop_to_rgb565le(full_frame_img, stage_box)
            send_rect_patch(12, 34, 208 - 1, 310 - 1, stage_payload)

            # PATCH 2: Clock & Status Header (X=305..470, Y=4..24)
            clock_payload = crop_to_rgb565le(full_frame_img, clock_box)
            send_rect_patch(305, 4, 470 - 1, 24 - 1, clock_payload)

            # PATCH 3: CPU Metrics Card Body (X=225..465, Y=48..118)
            cpu_payload = crop_to_rgb565le(full_frame_img, cpu_box)
            send_rect_patch(225, 48, 465 - 1, 118 - 1, cpu_payload)

            # PATCH 4: RAM Metrics Card Body (X=225..465, Y=142..212)
            ram_payload = crop_to_rgb565le(full_frame_img, ram_box)
            send_rect_patch(225, 142, 465 - 1, 212 - 1, ram_payload)

            frame_idx = (frame_idx + 1) % 6
            time.sleep(1.0)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print("Loop error:", exc)
            time.sleep(1.0)

    try:
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)
    except Exception:
        pass


if __name__ == "__main__":
    main()
