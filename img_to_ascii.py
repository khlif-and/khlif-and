"""Convert an image to ASCII art for GitHub profile README."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ASCII_RAMP_DENSE = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
ASCII_RAMP_SIMPLE = "@%#*+=-:. "
ASCII_RAMP_BLOCK = "█▓▒░ "


def image_to_ascii(
    image_path: Path,
    width: int,
    ramp: str,
    invert: bool,
    alpha_threshold: int,
) -> str:
    image = Image.open(image_path).convert("RGBA")
    original_width, original_height = image.size
    aspect_ratio = original_height / original_width
    # Terminal characters are ~2x taller than wide.
    new_height = max(1, int(width * aspect_ratio * 0.5))
    image = image.resize((width, new_height))

    grayscale = image.convert("L")
    alpha = image.split()[-1]

    if invert:
        ramp = ramp[::-1]

    ramp_last_index = len(ramp) - 1
    lines: list[str] = []
    for y in range(new_height):
        row_chars: list[str] = []
        for x in range(width):
            if alpha.getpixel((x, y)) < alpha_threshold:
                row_chars.append(" ")
                continue
            pixel = grayscale.getpixel((x, y))
            ramp_index = int(pixel / 255 * ramp_last_index)
            row_chars.append(ramp[ramp_index])
        lines.append("".join(row_chars).ljust(width))

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source image (PNG, JPG, ...)")
    parser.add_argument("-o", "--output", type=Path, help="Output text file")
    parser.add_argument("-w", "--width", type=int, default=60, help="Output width in chars")
    parser.add_argument(
        "-r",
        "--ramp",
        choices=("dense", "simple", "block"),
        default="dense",
        help="Character ramp style",
    )
    parser.add_argument("--invert", action="store_true", help="Invert brightness mapping")
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=64,
        help="Treat pixels below this alpha as transparent (0-255)",
    )
    args = parser.parse_args()

    ramp_map = {
        "dense": ASCII_RAMP_DENSE,
        "simple": ASCII_RAMP_SIMPLE,
        "block": ASCII_RAMP_BLOCK,
    }

    result = image_to_ascii(
        image_path=args.input,
        width=args.width,
        ramp=ramp_map[args.ramp],
        invert=args.invert,
        alpha_threshold=args.alpha_threshold,
    )

    if args.output:
        args.output.write_text(result, encoding="utf-8")
        print(f"Saved {len(result.splitlines())} lines to {args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()
