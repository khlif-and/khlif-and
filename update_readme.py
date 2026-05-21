"""Refresh dynamic stats inside README.md.

The README has labeled fields shaped like:

    . Age: ............ ...
    . Public Repos: ........ ...

This script keeps the prefix (label + dotted padding) and replaces the value
that follows. Markers are line-based so they render cleanly inside fenced
code blocks (HTML comments are not stripped there by GitHub).
"""

from __future__ import annotations

import json
import os
import re
import sys
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BIRTH_DATE = date(2003, 4, 1)
README_PATH = Path(__file__).resolve().parent / "README.md"
GITHUB_API = "https://api.github.com/users/{username}"


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
    def unit(value: int, singular: str) -> str:
        return f"{value} {singular}" if value == 1 else f"{value} {singular}s"

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


def replace_dotted_field(content: str, label: str, value: str) -> str:
    pattern = re.compile(
        rf"^(.*?\.\s+{re.escape(label)}:\s+\.+\s+).*$",
        flags=re.MULTILINE,
    )
    return pattern.sub(lambda m: f"{m.group(1)}{value}", content)


def replace_refresh_line(content: str, timestamp: str) -> str:
    pattern = re.compile(
        r"^(.*?\.\s+Last refreshed:\s+).*?(\s*\(auto-updated[^)]*\))\s*$",
        flags=re.MULTILINE,
    )
    return pattern.sub(lambda m: f"{m.group(1)}{timestamp} {m.group(2).strip()}", content)


def main() -> int:
    username = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("GITHUB_USERNAME", "")
    ).strip()

    if not username:
        print("Usage: python update_readme.py <github-username>", file=sys.stderr)
        return 2

    today = date.today()
    years, months, days = calculate_age(BIRTH_DATE, today)
    age_str = format_age(years, months, days)

    try:
        user = fetch_github_user(username, os.environ.get("GITHUB_TOKEN"))
    except (HTTPError, URLError) as exc:
        print(f"Failed to fetch GitHub user '{username}': {exc}", file=sys.stderr)
        return 1

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    dotted_fields = {
        "Age": age_str,
        "Public Repos": str(user.get("public_repos", 0)),
        "Public Gists": str(user.get("public_gists", 0)),
        "Followers": str(user.get("followers", 0)),
        "Following": str(user.get("following", 0)),
    }

    content = README_PATH.read_text(encoding="utf-8")
    for label, value in dotted_fields.items():
        content = replace_dotted_field(content, label, value)
    content = replace_refresh_line(content, updated_at)

    README_PATH.write_text(content, encoding="utf-8")

    print(f"Updated README for @{username}:")
    for label, value in dotted_fields.items():
        print(f"  {label}: {value}")
    print(f"  Last refreshed: {updated_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
