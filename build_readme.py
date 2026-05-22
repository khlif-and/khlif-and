"""Render a neofetch-style profile card as a single SVG image.

The SVG embeds:
- Anya ASCII art sampled from anya.png, with each character colored by the
  source pixel's RGB.
- A right-hand info panel themed with Tokyonight colors.

Dynamic fields (age, followers, following, repos, gists, last refreshed) are
recomputed each run. README.md is regenerated to embed the SVG.
"""

from __future__ import annotations

import json
import os
import sys
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE_IMAGE = ROOT / "anya.png"
OUTPUT_SVG = ROOT / "neofetch.svg"
README_FILE = ROOT / "README.md"

BIRTH_DATE = date(2003, 4, 1)
GITHUB_API = "https://api.github.com/users/{username}"

CHAR_WIDTH = 9
LINE_HEIGHT = 18
PADDING = 24
ASCII_WIDTH_CHARS = 48
INFO_GAP = 32
ALPHA_THRESHOLD = 64
BRIGHTNESS_BG_THRESHOLD = 30
QUANTIZE_COLORS = 32

ASCII_RAMP = "@%#*+=-:. "

PALETTE = {
    "bg": "#1a1b26",
    "header": "#e0af68",
    "label": "#7aa2f7",
    "value": "#c0caf5",
    "separator": "#bb9af7",
    "dim": "#565f89",
}


def calculate_age(birth: date, today: date) -> tuple[int, int, int]:
    years = today.year - birth.year
    months = today.month - birth.month
    days = today.day - birth.day

    if days < 0:
        months -= 1
        prev_month = today.month - 1 if today.month > 1 else 12
        prev_year = today.year if today.month > 1 else today.year - 1
        days += monthrange(prev_year, prev_month)[1]

    if months < 0:
        years -= 1
        months += 12

    return years, months, days


def format_age(years: int, months: int, days: int) -> str:
    def unit(value: int, label: str) -> str:
        return f"{value} {label}" if value == 1 else f"{value} {label}s"

    return f"{unit(years, 'year')}, {unit(months, 'month')}, {unit(days, 'day')}"


def fetch_github_user(username: str, token: str | None) -> dict:
    request = Request(
        GITHUB_API.format(username=username),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"profile-readme-updater/{username}",
        },
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def sample_colored_ascii(image_path: Path, width: int) -> list[list[tuple[str, str | None]]]:
    image = Image.open(image_path).convert("RGBA")
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
            if brightness < BRIGHTNESS_BG_THRESHOLD:
                row.append((" ", None))
                continue
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
        text = escape(chars).replace(" ", " ")
        if color is None:
            tspans.append(f"<tspan>{text}</tspan>")
        else:
            tspans.append(f'<tspan fill="{color}">{text}</tspan>')
    return f'<text x="{x}" y="{y}" xml:space="preserve">{"".join(tspans)}</text>'


def build_info_lines(age: str, stats: dict, updated: str) -> list[tuple[str, str]]:
    sep = "─"
    lines: list[tuple[str, str]] = [
        ("header", f"khlif-and@dev " + sep * 32),
        ("blank", ""),
        ("kv", f". Name: ............ Khalif Siregar"),
        ("kv", f". Age: ............. {age}"),
        ("kv", f". OS: .............. Windows 11"),
        ("kv", f". IDE: ............. VSCode, Neovim"),
        ("blank", ""),
        ("section", ". Languages.Programming " + sep * 22),
        ("kv", ".   Kotlin, Dart, Python, Java, Go"),
        ("section", ". Languages.Real " + sep * 30),
        ("kv", ".   Indonesian, English, German, Dutch"),
        ("blank", ""),
        ("section", ". Hobby " + sep * 39),
        ("kv", ".   Anime, Coding, Gaming"),
        ("blank", ""),
        ("section", ". Contact " + sep * 37),
        ("kv", f". Email: ........... khalifsiregar123@gmail.com"),
        ("kv", f". GitHub: .......... @khlif-and"),
        ("blank", ""),
        ("section", ". GitHub Stats " + sep * 32),
        ("kv", f". Followers: ....... {stats['followers']}"),
        ("kv", f". Following: ....... {stats['following']}"),
        ("kv", f". Public Repos: .... {stats['repos']}"),
        ("kv", f". Public Gists: .... {stats['gists']}"),
        ("blank", ""),
        ("dim", f". Last refreshed: {updated}"),
    ]
    return lines


def info_runs(kind: str, text: str) -> list[tuple[str | None, str]]:
    if not text:
        return []
    if kind == "header":
        if "─" in text:
            sep_start = text.index("─")
            return [
                (PALETTE["header"], text[:sep_start]),
                (PALETTE["separator"], text[sep_start:]),
            ]
        return [(PALETTE["header"], text)]
    if kind == "section":
        if "─" in text:
            sep_start = text.index("─")
            return [
                (PALETTE["label"], text[:sep_start]),
                (PALETTE["separator"], text[sep_start:]),
            ]
        return [(PALETTE["label"], text)]
    if kind == "kv":
        if ":" in text:
            colon_idx = text.index(":")
            label = text[: colon_idx + 1]
            value = text[colon_idx + 1 :]
            return [
                (PALETTE["label"], label),
                (PALETTE["value"], value),
            ]
        return [(PALETTE["value"], text)]
    if kind == "dim":
        return [(PALETTE["dim"], text)]
    return [(PALETTE["value"], text)]


def render_svg(
    ascii_rows: list[list[tuple[str, str | None]]],
    info_lines: list[tuple[str, str]],
) -> str:
    ascii_pixel_width = ASCII_WIDTH_CHARS * CHAR_WIDTH
    info_x = PADDING + ascii_pixel_width + INFO_GAP
    longest_info = max((len(text) for _, text in info_lines), default=0)
    width = info_x + longest_info * CHAR_WIDTH + PADDING
    line_count = max(len(ascii_rows), len(info_lines))
    height = PADDING * 2 + line_count * LINE_HEIGHT

    body: list[str] = []
    for i, row in enumerate(ascii_rows):
        y = PADDING + (i + 1) * LINE_HEIGHT - 4
        runs = group_runs(row)
        body.append(render_text(PADDING, y, runs))

    for i, (kind, text) in enumerate(info_lines):
        if kind == "blank":
            continue
        y = PADDING + (i + 1) * LINE_HEIGHT - 4
        body.append(render_text(info_x, y, info_runs(kind, text)))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        'font-family="\'JetBrains Mono\', \'Cascadia Code\', \'Fira Code\', \'Courier New\', monospace" '
        'font-size="14">\n'
        f'<rect width="100%" height="100%" fill="{PALETTE["bg"]}" rx="8"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def main() -> int:
    username = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("GITHUB_USERNAME", "khlif-and")
    ).strip()

    today = date.today()
    age = format_age(*calculate_age(BIRTH_DATE, today))

    try:
        user = fetch_github_user(username, os.environ.get("GITHUB_TOKEN"))
    except (HTTPError, URLError) as exc:
        print(f"Failed to fetch GitHub user '{username}': {exc}", file=sys.stderr)
        return 1

    stats = {
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "repos": user.get("public_repos", 0),
        "gists": user.get("public_gists", 0),
    }
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ascii_rows = sample_colored_ascii(SOURCE_IMAGE, ASCII_WIDTH_CHARS)
    info_lines = build_info_lines(age, stats, updated)
    svg = render_svg(ascii_rows, info_lines)
    OUTPUT_SVG.write_text(svg, encoding="utf-8")

    readme = (
        '<div align="center">\n\n'
        '<img src="neofetch.svg" alt="khlif-and neofetch" />\n\n'
        "</div>\n"
    )
    README_FILE.write_text(readme, encoding="utf-8")

    print(
        f"Generated {OUTPUT_SVG.name} ({len(svg)} bytes) and README for @{username}: "
        f"age={age}, {stats}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
