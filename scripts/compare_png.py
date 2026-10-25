#!/usr/bin/env python3
"""Compare encoded RGBA values without silently applying a color transform.

No third-party package is needed for non-interlaced 8-bit PNGs. Pillow is an
optional fallback for other PNG formats. A white/nonzero mask pixel includes a
pixel; black/transparent pixels exclude it. All pixels are included by default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_png(path: Path) -> dict:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    offset, chunks, ended = 8, [], False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if offset + length + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError("invalid PNG CRC")
        chunks.append((kind, payload))
        offset += length + 12
        if kind == b"IEND":
            ended = True
            break
    if not ended or not chunks or chunks[0][0] != b"IHDR":
        raise ValueError("PNG has no complete IHDR/IEND")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    if not width or not height or width * height > 100_000_000:
        raise ValueError("invalid or excessively large image dimensions")
    metadata = {}
    for kind, payload in chunks:
        if kind in (b"sRGB", b"gAMA", b"cHRM", b"iCCP", b"cICP"):
            metadata[kind.decode("ascii")] = payload.hex() if kind != b"iCCP" else hashlib.sha256(payload).hexdigest()
    info = {"width": width, "height": height, "bit_depth": depth,
            "color_type": color, "interlaced": bool(interlace),
            "color_metadata": metadata, "color_transform_applied": False}
    if depth == 16:
        raise ValueError("16-bit PNG comparison is unsupported; refusing lossy RGBA8 normalization")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if depth != 8 or interlace or not channels or compression or filtering:
        try:
            from PIL import Image
        except ImportError as error:
            raise ValueError("this PNG format needs optional Pillow") from error
        # Pillow convert() does not invoke ImageCms: no ICC conversion is applied.
        with Image.open(path) as image:
            info["rgba"] = image.convert("RGBA").tobytes()
        info["decoder"] = "Pillow; converted to RGBA8 without ICC transform"
        return info
    packed = zlib.decompress(b"".join(payload for kind, payload in chunks if kind == b"IDAT"))
    stride = width * channels
    if len(packed) != height * (stride + 1):
        raise ValueError("unexpected decompressed PNG length")
    unfiltered, previous = bytearray(), bytearray(stride)
    for row_index in range(height):
        start = row_index * (stride + 1)
        filter_type = packed[start]
        row = bytearray(packed[start + 1:start + 1 + stride])
        if filter_type > 4:
            raise ValueError("unknown PNG filter")
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up = previous[x]
            upper_left = previous[x - channels] if x >= channels else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                prediction = left + up - upper_left
                distances = (abs(prediction - left), abs(prediction - up), abs(prediction - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        unfiltered.extend(row)
        previous = row
    rgba = bytearray()
    palette = next((payload for kind, payload in chunks if kind == b"PLTE"), b"")
    transparency = next((payload for kind, payload in chunks if kind == b"tRNS"), b"")
    for i in range(0, len(unfiltered), channels):
        values = unfiltered[i:i + channels]
        if color == 6:
            rgba.extend(values)
        elif color == 2:
            alpha = 0 if len(transparency) == 6 and tuple(values) == struct.unpack(">HHH", transparency) else 255
            rgba.extend((*values, alpha))
        elif color == 0:
            alpha = 0 if len(transparency) == 2 and values[0] == struct.unpack(">H", transparency)[0] else 255
            rgba.extend((values[0], values[0], values[0], alpha))
        elif color == 4:
            rgba.extend((values[0], values[0], values[0], values[1]))
        else:
            index = values[0]
            if index * 3 + 3 > len(palette):
                raise ValueError("PNG palette index out of range")
            rgba.extend((*palette[index * 3:index * 3 + 3], transparency[index] if index < len(transparency) else 255))
    info["rgba"], info["decoder"] = bytes(rgba), "stdlib PNG RGBA8"
    return info


def compare_images(reference: Path, actual: Path, mask: Path | None = None,
                   channel_tolerance: int = 0, max_different_fraction: float = 0.0) -> dict:
    report = {"status": "incomplete", "comparison_space": "encoded RGBA8 values; no color transform",
              "alpha_policy": "compare alpha as a fourth channel; do not premultiply",
              "channel_tolerance": channel_tolerance, "max_different_fraction": max_different_fraction,
              "mask": {"policy": "include all pixels"}}
    if not 0 <= channel_tolerance <= 255 or not 0 <= max_different_fraction <= 1:
        report["reason"] = "invalid tolerance"
        return report
    try:
        ref, image = read_png(reference), read_png(actual)
        report["reference"] = {"path": str(reference.resolve()), "sha256": sha256(reference),
                               **{k: v for k, v in ref.items() if k != "rgba"}}
        report["actual"] = {"path": str(actual.resolve()), "sha256": sha256(actual),
                            **{k: v for k, v in image.items() if k != "rgba"}}
        if (ref["width"], ref["height"]) != (image["width"], image["height"]):
            report.update(status="failed", reason="image dimensions differ")
            return report
        count = ref["width"] * ref["height"]
        included = bytearray(b"\x01") * count
        if mask:
            mask_image = read_png(mask)
            if (ref["width"], ref["height"]) != (mask_image["width"], mask_image["height"]):
                report.update(status="failed", reason="mask dimensions differ")
                return report
            for pixel in range(count):
                values = mask_image["rgba"][pixel * 4:pixel * 4 + 4]
                included[pixel] = int(any(values[:3]) and values[3] > 0)
            report["mask"] = {"policy": "nonzero RGB and nonzero alpha includes pixel; binary inclusion",
                              "path": str(mask.resolve()), "sha256": sha256(mask)}
        selected = sum(included)
        report["mask"].update(included_pixels=selected, excluded_pixels=count - selected)
        if not selected:
            report.update(status="failed", reason="mask excludes every pixel")
            return report
        different, alpha_different, total_abs, total_squared, maximum = 0, 0, 0, 0, 0
        for pixel in range(count):
            if not included[pixel]:
                continue
            start = pixel * 4
            differences = [abs(a - b) for a, b in zip(ref["rgba"][start:start + 4], image["rgba"][start:start + 4])]
            different += int(max(differences) > channel_tolerance)
            alpha_different += int(differences[3] > channel_tolerance)
            total_abs += sum(differences)
            total_squared += sum(value * value for value in differences)
            maximum = max(maximum, *differences)
        fraction = different / selected
        metadata_equal = ref["color_metadata"] == image["color_metadata"]
        report.update(different_pixels=different, different_pixel_fraction=fraction,
                      alpha_different_pixels=alpha_different, max_channel_error=maximum,
                      mean_absolute_channel_error=total_abs / (selected * 4),
                      rms_channel_error=math.sqrt(total_squared / (selected * 4)),
                      color_metadata_equal=metadata_equal,
                      color_space_description="both untagged; transfer function unspecified" if not ref["color_metadata"] and not image["color_metadata"] else "PNG color metadata compared byte-for-byte",
                      status="passed" if metadata_equal and fraction <= max_different_fraction else "failed")
        if not metadata_equal:
            report["reason"] = "color metadata differs; no implicit color conversion is permitted"
    except (OSError, ValueError, zlib.error, struct.error) as error:
        report["reason"] = f"{type(error).__name__}: {error}"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--channel-tolerance", type=int, default=0)
    parser.add_argument("--max-different-fraction", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = compare_images(arguments.reference, arguments.actual, arguments.mask,
                            arguments.channel_tolerance, arguments.max_different_fraction)
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
