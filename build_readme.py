"""Generate README.md by combining ASCII art with profile info.

Run locally to bootstrap the file, and re-run via GitHub Actions to refresh
dynamic fields (age, followers, following, repos, gists, last refreshed).
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

ROOT = Path(__file__).resolve().parent
ASCII_FILE = ROOT / "anya.txt"
README_FILE = ROOT / "README.md"

BIRTH_DATE = date(2003, 4, 1)
GITHUB_API = "https://api.github.com/users/{username}"
ASCII_WIDTH = 45
GAP = "    "

HEADER_FORMAT = "khlif-and@dev " + "─" * 38


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


def build_info_lines(age: str, stats: dict, updated: str) -> list[str]:
    return [
        HEADER_FORMAT,
        "",
        f". Name: .............. Khalif Siregar",
        f". Age: ............... {age}",
        f". OS: ................ Windows 11",
        f". IDE: ............... VSCode, Neovim",
        "",
        ". Languages.Programming " + "─" * 25,
        ".   Kotlin, Dart, Python, Java, Go",
        ". Languages.Real " + "─" * 32,
        ".   Indonesian, English, German, Dutch",
        "",
        ". Hobby " + "─" * 41,
        ".   Anime, Coding, Gaming",
        "",
        ". Contact " + "─" * 39,
        f". Email: ............. khalifsiregar123@gmail.com",
        f". GitHub: ............ @khlif-and",
        "",
        ". GitHub Stats " + "─" * 34,
        f". Followers: ......... {stats['followers']}",
        f". Following: ......... {stats['following']}",
        f". Public Repos: ...... {stats['repos']}",
        f". Public Gists: ...... {stats['gists']}",
        "",
        f". Last refreshed: {updated}",
    ]


def combine_columns(ascii_lines: list[str], info_lines: list[str]) -> list[str]:
    max_len = max(len(ascii_lines), len(info_lines))
    combined: list[str] = []
    for i in range(max_len):
        left = ascii_lines[i] if i < len(ascii_lines) else " " * ASCII_WIDTH
        right = info_lines[i] if i < len(info_lines) else ""
        combined.append(f"{left.ljust(ASCII_WIDTH)}{GAP}{right}".rstrip())
    return combined


def render_readme(combined_lines: list[str]) -> str:
    body = "\n".join(combined_lines)
    cards = (
        "<div align=\"center\">\n\n"
        "![Stats](https://github-readme-stats.vercel.app/api"
        "?username=khlif-and&show_icons=true&theme=tokyonight&hide_border=true&count_private=true)\n"
        "![Top Languages](https://github-readme-stats.vercel.app/api/top-langs/"
        "?username=khlif-and&layout=compact&theme=tokyonight&hide_border=true&langs_count=8)\n"
        "![Streak](https://streak-stats.demolab.com?user=khlif-and&theme=tokyonight&hide_border=true)\n\n"
        "</div>\n"
    )
    return f"```apache\n{body}\n```\n\n{cards}"


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

    ascii_lines = ASCII_FILE.read_text(encoding="utf-8").splitlines()
    info_lines = build_info_lines(age, stats, updated)
    combined = combine_columns(ascii_lines, info_lines)
    README_FILE.write_text(render_readme(combined), encoding="utf-8")

    print(f"README rendered for @{username}: age={age}, {stats}, updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
