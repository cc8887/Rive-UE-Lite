#!/usr/bin/env python3
"""Inspect actual RGBA pixels so a matching pair of blank images is visible."""
import argparse
from collections import Counter
import json
from pathlib import Path
from compare_png import read_png, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = []
    for path in args.images:
        image = read_png(path)
        rgba = image.pop("rgba")
        colors = Counter(rgba[offset:offset + 4] for offset in range(0, len(rgba), 4))
        alphas = rgba[3::4]
        rows.append({"path": str(path.resolve()), "sha256": sha256(path), **image,
                     "unique_rgba_values": len(colors),
                     "nontransparent_pixels": sum(value > 0 for value in alphas),
                     "alpha_min": min(alphas), "alpha_max": max(alphas),
                     "most_common_rgba": [{"rgba": list(color), "pixels": count}
                                          for color, count in colors.most_common(5)],
                     "scope": "pixel-content inspection only; UE capture provenance and equality are separate gates"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
