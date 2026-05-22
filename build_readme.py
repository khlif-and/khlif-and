"""Render the GitHub profile README.

Generates neofetch.svg (Anya neofetch card) and, when a token is available,
stats.svg (GitHub stats panel). README.md is regenerated to embed both.
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

from render import (
    CHAR_WIDTH,
    INFO_GAP,
    LINE_HEIGHT,
    PADDING,
    PALETTE,
    group_runs,
    render_text,
    sample_colored_ascii,
    svg_close,
    svg_open,
)
from stats import build_stats_svg, fetch_stats

ROOT = Path(__file__).resolve().parent
ANYA_IMAGE = ROOT / "anya.png"
MASCOTS_IMAGE = ROOT / "mascots.png"
NEOFETCH_SVG = ROOT / "neofetch.svg"
STATS_SVG = ROOT / "stats.svg"
README_FILE = ROOT / "README.md"

BIRTH_DATE = date(2003, 4, 1)
GITHUB_API_USER = "https://api.github.com/users/{username}"
ANYA_WIDTH_CHARS = 48


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
        GITHUB_API_USER.format(username=username),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"profile-readme-updater/{username}",
        },
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def build_info_lines(age: str, stats: dict, updated: str) -> list[tuple[str, str]]:
    sep = "─"
    return [
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
            return [
                (PALETTE["label"], text[: colon_idx + 1]),
                (PALETTE["value"], text[colon_idx + 1 :]),
            ]
        return [(PALETTE["value"], text)]
    if kind == "dim":
        return [(PALETTE["dim"], text)]
    return [(PALETTE["value"], text)]


def render_neofetch_svg(
    ascii_rows: list[list[tuple[str, str | None]]],
    info_lines: list[tuple[str, str]],
) -> str:
    ascii_pixel_width = ANYA_WIDTH_CHARS * CHAR_WIDTH
    info_x = PADDING + ascii_pixel_width + INFO_GAP
    longest_info = max((len(text) for _, text in info_lines), default=0)
    width = info_x + longest_info * CHAR_WIDTH + PADDING
    line_count = max(len(ascii_rows), len(info_lines))
    height = PADDING * 2 + line_count * LINE_HEIGHT

    body: list[str] = []
    for i, row in enumerate(ascii_rows):
        y = PADDING + (i + 1) * LINE_HEIGHT - 4
        body.append(render_text(PADDING, y, group_runs(row)))

    for i, (kind, text) in enumerate(info_lines):
        if kind == "blank":
            continue
        y = PADDING + (i + 1) * LINE_HEIGHT - 4
        body.append(render_text(info_x, y, info_runs(kind, text)))

    return svg_open(width, height) + "\n".join(body) + svg_close()


def write_readme(stats_available: bool) -> None:
    parts = [
        '<div align="center">\n\n',
        '<img src="neofetch.svg" alt="khlif-and neofetch" />\n',
    ]
    if stats_available:
        parts.append('\n<br/>\n\n<img src="stats.svg" alt="khlif-and github stats" />\n')
    parts.append('\n</div>\n')
    README_FILE.write_text("".join(parts), encoding="utf-8")


def main() -> int:
    username = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("GITHUB_USERNAME", "khlif-and")
    ).strip()
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")

    today = date.today()
    age = format_age(*calculate_age(BIRTH_DATE, today))
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        user = fetch_github_user(username, token)
    except (HTTPError, URLError) as exc:
        print(f"Failed to fetch GitHub user '{username}': {exc}", file=sys.stderr)
        return 1

    basic_stats = {
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "repos": user.get("public_repos", 0),
        "gists": user.get("public_gists", 0),
    }
    ascii_rows = sample_colored_ascii(ANYA_IMAGE, ANYA_WIDTH_CHARS)
    info_lines = build_info_lines(age, basic_stats, updated)
    NEOFETCH_SVG.write_text(render_neofetch_svg(ascii_rows, info_lines), encoding="utf-8")

    stats_rendered = False
    if token and MASCOTS_IMAGE.exists():
        try:
            stats_data = fetch_stats(username, token, today)
            STATS_SVG.write_text(
                build_stats_svg(stats_data, MASCOTS_IMAGE, updated), encoding="utf-8"
            )
            stats_rendered = True
        except (HTTPError, URLError, RuntimeError) as exc:
            print(f"Failed to render stats.svg: {exc}", file=sys.stderr)
    elif not token:
        print("No GH_PAT/GITHUB_TOKEN available — skipping stats.svg", file=sys.stderr)
    elif not MASCOTS_IMAGE.exists():
        print(f"Missing {MASCOTS_IMAGE.name} — skipping stats.svg", file=sys.stderr)

    write_readme(stats_rendered or STATS_SVG.exists())

    print(
        f"Generated {NEOFETCH_SVG.name} for @{username}: age={age}, {basic_stats}"
        + (f"; stats.svg refreshed" if stats_rendered else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
