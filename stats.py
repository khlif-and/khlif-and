"""GitHub stats: GraphQL fetchers, streak computation, and stats.svg rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

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

GITHUB_GRAPHQL = "https://api.github.com/graphql"
STREAK_START = date(2025, 1, 1)

MASCOT_WIDTH_CHARS = 20
MASCOT_FLOODFILL_TOLERANCE = 18
LANGUAGE_DEFAULT_COLOR = "#9aa5ce"
LANGUAGES_TOP_N = 5
REPOS_TOP_N = 5
BAR_WIDTH = 10

MASCOT_LANGUAGES = "languages"
MASCOT_STREAK = "streak"
MASCOT_REPOS = "repos"
MASCOT_TOTALS = "totals"

LANGUAGES_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 50, ownerAffiliations: OWNER, isFork: false, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

WINDOW_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
      commitContributionsByRepository(maxRepositories: 25) {
        repository {
          name
          nameWithOwner
          primaryLanguage { name color }
        }
        contributions { totalCount }
      }
    }
  }
}
"""

YEAR_TOTAL_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { totalContributions }
    }
  }
}
"""


@dataclass
class LanguageStat:
    name: str
    color: str
    size: int


@dataclass
class RepoStat:
    name: str
    full_name: str
    language: str | None
    language_color: str | None
    commits: int


@dataclass
class StatsData:
    languages: list[LanguageStat]
    languages_total: int
    streak_days: int
    streak_start: date | None
    streak_end: date | None
    repos: list[RepoStat]
    total_2025: int
    total_alltime: int


@dataclass
class WindowResult:
    created_at: date
    total: int
    days: list[tuple[date, int]]
    repo_commits: dict[str, RepoStat]


def graphql(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        GITHUB_GRAPHQL,
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-readme-updater",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def yearly_windows(start: date, end: date) -> list[tuple[date, date]]:
    if start > end:
        return []
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(date(cursor.year, 12, 31), end)
        windows.append((cursor, window_end))
        cursor = date(cursor.year + 1, 1, 1)
    return windows


def to_iso(d: date, end_of_day: bool = False) -> str:
    moment = (
        datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
        if end_of_day
        else datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    )
    return moment.isoformat()


def fetch_languages(username: str, token: str) -> list[LanguageStat]:
    totals: dict[str, tuple[int, str]] = {}
    cursor: str | None = None
    while True:
        data = graphql(LANGUAGES_QUERY, {"login": username, "cursor": cursor}, token)
        repos = data["user"]["repositories"]
        for node in repos["nodes"]:
            for edge in node["languages"]["edges"]:
                node_data = edge["node"]
                name = node_data["name"]
                color = node_data["color"] or LANGUAGE_DEFAULT_COLOR
                prev_size, _ = totals.get(name, (0, color))
                totals[name] = (prev_size + edge["size"], color)
        page = repos["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    return sorted(
        (LanguageStat(name=n, color=c, size=s) for n, (s, c) in totals.items()),
        key=lambda lang: lang.size,
        reverse=True,
    )


def fetch_window(username: str, token: str, start: date, end: date) -> WindowResult:
    data = graphql(
        WINDOW_QUERY,
        {"login": username, "from": to_iso(start), "to": to_iso(end, end_of_day=True)},
        token,
    )
    user = data["user"]
    created_at = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00")).date()
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days: list[tuple[date, int]] = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            day_date = date.fromisoformat(day["date"])
            if start <= day_date <= end:
                days.append((day_date, day["contributionCount"]))
    repo_commits: dict[str, RepoStat] = {}
    for entry in user["contributionsCollection"]["commitContributionsByRepository"]:
        repo = entry["repository"]
        lang = repo["primaryLanguage"]
        repo_commits[repo["nameWithOwner"]] = RepoStat(
            name=repo["name"],
            full_name=repo["nameWithOwner"],
            language=lang["name"] if lang else None,
            language_color=lang["color"] if lang and lang.get("color") else None,
            commits=entry["contributions"]["totalCount"],
        )
    return WindowResult(
        created_at=created_at,
        total=calendar["totalContributions"],
        days=days,
        repo_commits=repo_commits,
    )


def fetch_year_total(username: str, token: str, start: date, end: date) -> int:
    data = graphql(
        YEAR_TOTAL_QUERY,
        {"login": username, "from": to_iso(start), "to": to_iso(end, end_of_day=True)},
        token,
    )
    return data["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]


def compute_current_streak(
    days: Iterable[tuple[date, int]], today: date
) -> tuple[int, date | None, date | None]:
    by_date = {d: c for d, c in days}
    cursor = today
    if by_date.get(cursor, 0) == 0:
        cursor = today - timedelta(days=1)
    streak = 0
    end_d: date | None = None
    while by_date.get(cursor, 0) > 0:
        if end_d is None:
            end_d = cursor
        streak += 1
        cursor -= timedelta(days=1)
    start_d = cursor + timedelta(days=1) if streak > 0 else None
    return streak, start_d, end_d


def fetch_stats(username: str, token: str, today: date) -> StatsData:
    streak_days: list[tuple[date, int]] = []
    repo_commits: dict[str, RepoStat] = {}
    total_2025 = 0
    created_at: date | None = None

    for start, end in yearly_windows(STREAK_START, today):
        result = fetch_window(username, token, start, end)
        created_at = result.created_at
        streak_days.extend(result.days)
        total_2025 += result.total
        for key, stat in result.repo_commits.items():
            if key in repo_commits:
                repo_commits[key].commits += stat.commits
            else:
                repo_commits[key] = stat

    total_alltime = total_2025
    if created_at and created_at < STREAK_START:
        pre_end = STREAK_START - timedelta(days=1)
        for start, end in yearly_windows(created_at, pre_end):
            total_alltime += fetch_year_total(username, token, start, end)

    all_languages = fetch_languages(username, token)
    languages_total = sum(lang.size for lang in all_languages)
    top_languages = all_languages[:LANGUAGES_TOP_N]
    top_repos = sorted(repo_commits.values(), key=lambda r: r.commits, reverse=True)[:REPOS_TOP_N]
    streak, streak_start, streak_end = compute_current_streak(streak_days, today)

    return StatsData(
        languages=top_languages,
        languages_total=languages_total,
        streak_days=streak,
        streak_start=streak_start,
        streak_end=streak_end,
        repos=top_repos,
        total_2025=total_2025,
        total_alltime=total_alltime,
    )


def crop_mascots(source: Path) -> dict[str, Image.Image]:
    image = Image.open(source).convert("RGBA")
    w, h = image.size
    mid_x, mid_y = w // 2, h // 2
    quadrants = {
        MASCOT_LANGUAGES: image.crop((0, 0, mid_x, mid_y)),
        MASCOT_STREAK: image.crop((mid_x, 0, w, mid_y)),
        MASCOT_REPOS: image.crop((0, mid_y, mid_x, h)),
        MASCOT_TOTALS: image.crop((mid_x, mid_y, w, h)),
    }
    return {key: remove_background(img) for key, img in quadrants.items()}


def remove_background(image: Image.Image, tolerance: int = MASCOT_FLOODFILL_TOLERANCE) -> Image.Image:
    image = image.convert("RGBA").copy()
    w, h = image.size
    transparent = (0, 0, 0, 0)
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        try:
            ImageDraw.floodfill(image, corner, transparent, thresh=tolerance)
        except (ValueError, IndexError):
            continue
    return image


def progress_bar(ratio: float, width: int = BAR_WIDTH) -> tuple[str, str]:
    filled = max(0, min(width, round(ratio * width)))
    return "█" * filled, "░" * (width - filled)


def format_int(n: int) -> str:
    return f"{n:,}"


def format_streak_range(start: date | None, end: date | None) -> str:
    if not start or not end:
        return "no active streak"
    if start == end:
        return start.isoformat()
    return f"{start.isoformat()} → {end.isoformat()}"


@dataclass
class Section:
    mascot_key: str
    title: str
    lines: list[list[tuple[str, str]]]


def build_section_lines(stats: StatsData) -> list[Section]:
    sections: list[Section] = []

    lang_lines: list[list[tuple[str, str]]] = []
    if stats.languages_total > 0:
        for lang in stats.languages:
            ratio = lang.size / stats.languages_total
            filled, empty = progress_bar(ratio)
            lang_lines.append([
                (PALETTE["label"], f".   {lang.name:<14}"),
                (PALETTE["value"], " "),
                (lang.color, filled),
                (PALETTE["bar_empty"], empty),
                (PALETTE["value"], f" {ratio * 100:5.1f}%"),
            ])
    else:
        lang_lines.append([(PALETTE["dim"], ".   no language data")])
    sections.append(Section(MASCOT_LANGUAGES, ". Top Languages", lang_lines))

    streak_lines: list[list[tuple[str, str]]] = []
    if stats.streak_days > 0:
        streak_lines.append([
            (PALETTE["label"], ".   Current streak: "),
            (PALETTE["accent"], f"{stats.streak_days} days"),
        ])
        streak_lines.append([
            (PALETTE["label"], ".   Range: "),
            (PALETTE["value"], format_streak_range(stats.streak_start, stats.streak_end)),
        ])
    else:
        streak_lines.append([(PALETTE["dim"], ".   no active streak since 2025-01-01")])
    streak_lines.append([
        (PALETTE["label"], ".   Window: "),
        (PALETTE["value"], f"{STREAK_START.isoformat()} → today"),
    ])
    sections.append(Section(MASCOT_STREAK, ". Current Streak", streak_lines))

    repo_lines: list[list[tuple[str, str]]] = []
    if stats.repos:
        for idx, repo in enumerate(stats.repos, start=1):
            lang_name = repo.language or "—"
            lang_color = repo.language_color or LANGUAGE_DEFAULT_COLOR
            repo_lines.append([
                (PALETTE["label"], f".   {idx}. "),
                (PALETTE["value"], f"{repo.full_name:<32}"),
                (lang_color, f" {lang_name:<12}"),
                (PALETTE["accent"], f" {format_int(repo.commits):>6} commits"),
            ])
    else:
        repo_lines.append([(PALETTE["dim"], ".   no commit activity since 2025-01-01")])
    sections.append(Section(MASCOT_REPOS, ". Top Repos (by my commits since 2025)", repo_lines))

    totals_lines: list[list[tuple[str, str]]] = [
        [
            (PALETTE["label"], ".   All-time: "),
            (PALETTE["accent"], f"{format_int(stats.total_alltime)} contributions"),
        ],
        [
            (PALETTE["label"], ".   2025:     "),
            (PALETTE["accent"], f"{format_int(stats.total_2025)} contributions"),
        ],
    ]
    sections.append(Section(MASCOT_TOTALS, ". Totals", totals_lines))

    return sections


def render_section_title(title: str, total_width_chars: int) -> list[tuple[str, str]]:
    sep_count = max(3, total_width_chars - len(title) - 1)
    return [
        (PALETTE["label"], title + " "),
        (PALETTE["separator"], "─" * sep_count),
    ]


def render_stats_svg(stats: StatsData, mascots_image: Path, updated: str) -> str:
    mascots = crop_mascots(mascots_image)
    mascot_rows_by_key = {
        key: sample_colored_ascii(img, MASCOT_WIDTH_CHARS, drop_dark_bg=False, solid=True)
        for key, img in mascots.items()
    }
    mascot_height = max(len(rows) for rows in mascot_rows_by_key.values())

    sections = build_section_lines(stats)
    info_x = PADDING + MASCOT_WIDTH_CHARS * CHAR_WIDTH + INFO_GAP
    info_chars_width = 75

    body: list[str] = []
    line_index = 0

    header_runs: list[tuple[str | None, str]] = [
        (PALETTE["header"], "stats@github "),
        (PALETTE["separator"], "─" * 48),
    ]
    body.append(
        render_text(PADDING, PADDING + (line_index + 1) * LINE_HEIGHT - 4, header_runs)
    )
    line_index += 2  # header + blank

    for section_idx, section in enumerate(sections):
        section_top_line = line_index
        mascot_rows = mascot_rows_by_key[section.mascot_key]
        for row_idx, row in enumerate(mascot_rows):
            y = PADDING + (section_top_line + row_idx + 1) * LINE_HEIGHT - 4
            body.append(render_text(PADDING, y, group_runs(row)))

        title_runs = render_section_title(section.title, info_chars_width)
        body.append(
            render_text(info_x, PADDING + (section_top_line + 1) * LINE_HEIGHT - 4, title_runs)
        )
        for line_offset, runs in enumerate(section.lines, start=1):
            y = PADDING + (section_top_line + line_offset + 1) * LINE_HEIGHT - 4
            body.append(render_text(info_x, y, [(c, t) for c, t in runs]))

        section_height = max(mascot_height, len(section.lines) + 1)
        line_index += section_height
        if section_idx < len(sections) - 1:
            line_index += 1  # blank between sections

    line_index += 1  # blank before footer
    footer_runs: list[tuple[str | None, str]] = [
        (PALETTE["dim"], f". Last refreshed: {updated}")
    ]
    body.append(
        render_text(PADDING, PADDING + (line_index + 1) * LINE_HEIGHT - 4, footer_runs)
    )
    line_index += 1

    info_pixel_width = info_chars_width * CHAR_WIDTH
    width = info_x + info_pixel_width + PADDING
    height = PADDING * 2 + line_index * LINE_HEIGHT

    return svg_open(width, height) + "\n".join(body) + svg_close()


def build_stats_svg(stats: StatsData, mascots_image: Path, updated: str) -> str:
    return render_stats_svg(stats, mascots_image, updated)
