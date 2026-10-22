"""Render static/icon.ico (the same motif as static/icon.svg) with the stdlib only."""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "icon.ico"
SIZES = (16, 24, 32, 48, 64, 256)
BG = (0xC9, 0x64, 0x42)
FG = (0xFF, 0xFF, 0xFF)
# Strokes in the 64x64 design space of icon.svg: (x1, y1, x2, y2), width 6, round caps.
STROKES = ((18, 22, 28, 32), (28, 32, 18, 42), (32, 44, 46, 44))
HALF_STROKE = 3.0
RADIUS = 14.0
SAMPLES = 4


def _seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - x1 - t * dx, py - y1 - t * dy)


def _in_rounded_square(px, py):
    cx = min(max(px, RADIUS), 64 - RADIUS)
    cy = min(max(py, RADIUS), 64 - RADIUS)
    return 0 <= px <= 64 and 0 <= py <= 64 and math.hypot(px - cx, py - cy) <= RADIUS


def render(size):
    rows = []
    scale = 64 / size
    for y in range(size):
        row = bytearray([0])  # PNG filter type "none"
        for x in range(size):
            inside = ink = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    px = (x + (sx + 0.5) / SAMPLES) * scale
                    py = (y + (sy + 0.5) / SAMPLES) * scale
                    if _in_rounded_square(px, py):
                        inside += 1
                        if any(_seg_dist(px, py, *s) <= HALF_STROKE for s in STROKES):
                            ink += 1
            total = SAMPLES * SAMPLES
            mix = ink / inside if inside else 0
            rgb = [round(b + (f - b) * mix) for b, f in zip(BG, FG)]
            row += bytes(rgb + [round(255 * inside / total)])
        rows.append(bytes(row))
    return _png(size, b"".join(rows))


def _png(size, raw):
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))

    header = struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    images = [render(s) for s in SIZES]
    offset = 6 + 16 * len(images)
    directory, blobs = b"", b""
    for size, png in zip(SIZES, images):
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    OUT.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + directory + blobs)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
