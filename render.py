"""Shared rendering primitives for Tokyonight-themed SVG outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Union
from xml.sax.saxutils import escape

from PIL import Image

CHAR_WIDTH = 9
LINE_HEIGHT = 18
PADDING = 24
INFO_GAP = 32
ALPHA_THRESHOLD = 64
BRIGHTNESS_BG_THRESHOLD = 30
QUANTIZE_COLORS = 32

ASCII_RAMP = "@%#*+=-:. "
SOLID_BLOCK = "█"
NBSP = " "

PALETTE = {
    "bg": "#1a1b26",
    "header": "#e0af68",
    "label": "#7aa2f7",
    "value": "#c0caf5",
    "separator": "#bb9af7",
    "dim": "#565f89",
    "accent": "#9ece6a",
    "warn": "#f7768e",
    "bar_empty": "#414868",
}

FONT_STACK = (
    "'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Courier New', monospace"
)

ImageSource = Union[Path, Image.Image]


def sample_colored_ascii(
    source: ImageSource,
    width: int,
    *,
    drop_dark_bg: bool = True,
    solid: bool = False,
) -> list[list[tuple[str, str | None]]]:
    image = source.convert("RGBA") if isinstance(source, Image.Image) else Image.open(source).convert("RGBA")
    aspect = image.size[1] / image.size[0]
    height = max(1, int(width * aspect * 0.5))
    image = image.resize((width, height), Image.Resampling.LANCZOS)

    alpha = image.split()[-1]
    rgb_image = image.convert("RGB")
    quantized = rgb_image.quantize(colors=QUANTIZE_COLORS).convert("RGB")

    ramp_max = len(ASCII_RAMP) - 1
    rows: list[list[tuple[str, str | None]]] = []
    for y in range(height):
        row: list[tuple[str, str | None]] = []
        for x in range(width):
            if alpha.getpixel((x, y)) < ALPHA_THRESHOLD:
                row.append((" ", None))
                continue
            r, g, b = quantized.getpixel((x, y))
            brightness = r * 0.299 + g * 0.587 + b * 0.114
            if drop_dark_bg and brightness < BRIGHTNESS_BG_THRESHOLD:
                row.append((" ", None))
                continue
            if solid:
                char = SOLID_BLOCK
            else:
                ramp_index = int((1 - brightness / 255) * ramp_max)
                char = ASCII_RAMP[ramp_index]
            color = f"#{r:02x}{g:02x}{b:02x}"
            row.append((char, color))
        rows.append(row)
    return rows


def group_runs(row: list[tuple[str, str | None]]) -> list[tuple[str | None, str]]:
    runs: list[tuple[str | None, str]] = []
    current_color: str | None = "__INIT__"
    buffer: list[str] = []
    for char, color in row:
        if color != current_color:
            if buffer:
                runs.append((current_color, "".join(buffer)))
            current_color = color
            buffer = [char]
        else:
            buffer.append(char)
    if buffer:
        runs.append((current_color, "".join(buffer)))
    return runs


def render_text(x: int, y: int, runs: list[tuple[str | None, str]]) -> str:
    tspans: list[str] = []
    for color, chars in runs:
        text = escape(chars).replace(" ", NBSP)
        if color is None:
            tspans.append(f"<tspan>{text}</tspan>")
        else:
            tspans.append(f'<tspan fill="{color}">{text}</tspan>')
    return f'<text x="{x}" y="{y}" xml:space="preserve">{"".join(tspans)}</text>'


def svg_open(width: int, height: int) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="{FONT_STACK}" font-size="14">\n'
        f'<rect width="100%" height="100%" fill="{PALETTE["bg"]}" rx="8"/>\n'
    )


def svg_close() -> str:
    return "\n</svg>\n"
