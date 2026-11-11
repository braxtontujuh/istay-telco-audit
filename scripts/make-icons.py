"""Rasterize the project's simple, code-native signal-bar icon without external tools."""
import struct
import zlib
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "frontend/public"
for size in (192, 512):
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            px, py = x * 512 / size, y * 512 / size
            bar = any(a <= px < a + 64 and top <= py < 412 for a, top in ((100, 300), (224, 200), (348, 100)))
            pixels.extend((228, 185, 108) if bar else (18, 60, 59))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    result = b"\x89PNG\r\n\x1a\n"
    result += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    result += chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
    (root / f"icon-{size}.png").write_bytes(result)
