#!/usr/bin/env python3
"""Verify Peloton dashboard generated data against the scrubbed CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def classify(title: str) -> str | None:
    if "FTP Test" in title:
        return "FTP Test"
    if "Power Zone Max" in title:
        return "PZ Max"
    if (
        "Power Zone Endurance" in title
        or "Two for One Power Zone Endurance" in title
        or "Global Power Zone Endurance" in title
    ):
        return "PZ Endurance"
    if "Power Zone Ride" in title or "Power Zone EDM" in title or "Power Zone Pop" in title:
        return "PZ Standard"
    return None


def is_ancillary(row: dict[str, str]) -> bool:
    return "FTP Warm Up" in row["Title"] or row.get("Type", "") in ("Warm Up", "Cool Down")


def pos_float(value: str) -> float:
    if not value:
        return 0.0
    parsed = float(value)
    return parsed if parsed > 0 else 0.0


def consecutive_week_streaks(weeks: set[tuple[int, int]]) -> int:
    sorted_weeks = sorted(weeks)
    if not sorted_weeks:
        return 0
    longest = 1
    current = 1
    for index in range(1, len(sorted_weeks)):
        prev = datetime.fromisocalendar(*sorted_weeks[index - 1], 1)
        curr = datetime.fromisocalendar(*sorted_weeks[index], 1)
        if (curr - prev).days == 7:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def extract_embedded_data(html: str) -> dict:
    marker = "const DATA = "
    start = html.find(marker)
    if start == -1:
        raise ValueError("Could not find embedded DATA block in dashboard HTML")
    index = start + len(marker)
    if index >= len(html) or html[index] != "{":
        raise ValueError("Embedded DATA block does not start with an object")

    depth = 0
    in_string = False
    escape = False
    for end in range(index, len(html)):
        char = html[end]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[index : end + 1])
    raise ValueError("Could not find end of embedded DATA block")


def git_output(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def display_int(value: float | int) -> str:
    return f"{int(round(value)):,}"


def compact_calories(value: int) -> str:
    return f"{value / 1_000_000:.1f}M"


def format_long_date(date_str: str) -> str:
    date = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{date.strftime('%B')} {date.day}, {date.year}"


def calculate_from_csv(rows: list[dict[str, str]]) -> dict[str, float | int]:
    core_rows = [row for row in rows if not is_ancillary(row)]

    performance = []
    zero_watts_classified = 0
    for row in rows:
        if row["Fitness Discipline"] != "Cycling":
            continue
        if classify(row["Title"]) is None:
            continue
        if not row["Avg. Watts"]:
            zero_watts_classified += 1
            continue
        watts = float(row["Avg. Watts"])
        if watts == 0:
            zero_watts_classified += 1
            continue
        performance.append(row)

    active_weeks: set[tuple[int, int]] = set()
    for row in core_rows:
        date = datetime.strptime(row["Workout Timestamp"][:10], "%Y-%m-%d")
        iso_year, iso_week, _ = date.isocalendar()
        active_weeks.add((iso_year, iso_week))

    if active_weeks:
        first_week = datetime.fromisocalendar(*min(active_weeks), 1)
        last_week = datetime.fromisocalendar(*max(active_weeks), 1)
        active_week_span = ((last_week - first_week).days // 7) + 1
    else:
        active_week_span = 0

    active_months = {row["Workout Timestamp"][:7] for row in core_rows}
    if active_months:
        first_year, first_month = map(int, min(active_months).split("-"))
        last_year, last_month = map(int, max(active_months).split("-"))
        active_month_span = (last_year - first_year) * 12 + (last_month - first_month) + 1
    else:
        active_month_span = 0

    miles = round(sum(pos_float(row["Distance (mi)"]) for row in rows), 1)
    return {
        "total_workouts_raw": len(rows),
        "total_workouts": len(core_rows),
        "ancillary_workouts": len(rows) - len(core_rows),
        "performance_rides": len(performance),
        "total_hours": round(
            sum(int(row["Length (minutes)"]) for row in rows if row["Length (minutes)"]) / 60,
            1,
        ),
        "total_hours_core": round(
            sum(
                int(row["Length (minutes)"])
                for row in core_rows
                if row["Length (minutes)"]
            )
            / 60,
            1,
        ),
        "longest_week_streak": consecutive_week_streaks(active_weeks),
        "active_weeks": len(active_weeks),
        "active_week_span": active_week_span,
        "active_months": len(active_months),
        "active_month_span": active_month_span,
        "active_days": len({row["Workout Timestamp"][:10] for row in core_rows}),
        "miles": miles,
        "calories": int(sum(pos_float(row["Calories Burned"]) for row in rows)),
        "around_world_x": round(miles / 24901, 2),
        "rides_with_zero_watts": zero_watts_classified,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="Path to peloton-dashboard repo")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    csv_path = repo / "raw_data" / "peloton_workouts.csv"
    json_path = repo / "organized" / "dashboard_data.json"
    html_path = repo / "dashboard" / "dashboard.html"

    failures: list[str] = []

    rows = list(csv.DictReader(csv_path.open(newline="")))
    data = json.loads(json_path.read_text())
    embedded = extract_embedded_data(html_path.read_text())

    if embedded != data:
        failures.append("dashboard/dashboard.html embedded DATA does not match organized/dashboard_data.json")

    calc = calculate_from_csv(rows)
    expected = {
        **data["headline"],
        **data["volume"]["totals"],
        "rides_with_zero_watts": data["performance"]["data_quality_notes"][
            "rides_with_zero_watts"
        ],
    }
    compare_keys = [
        "total_workouts_raw",
        "total_workouts",
        "ancillary_workouts",
        "performance_rides",
        "total_hours",
        "total_hours_core",
        "longest_week_streak",
        "active_weeks",
        "active_week_span",
        "active_months",
        "active_month_span",
        "active_days",
        "miles",
        "calories",
        "around_world_x",
        "rides_with_zero_watts",
    ]

    rows_out = []
    for key in compare_keys:
        status = "OK" if calc[key] == expected[key] else "FAIL"
        if status == "FAIL":
            failures.append(f"{key}: csv={calc[key]} json={expected[key]}")
        rows_out.append((key, calc[key], expected[key], status))

    header = rows[0].keys() if rows else []
    if "Class Timestamp" in header:
        failures.append("raw_data/peloton_workouts.csv still contains Class Timestamp")
    full_ts_rows = [
        index
        for index, row in enumerate(rows, start=2)
        if re.search(r"\d{2}:\d{2}", row["Workout Timestamp"])
    ]
    if full_ts_rows:
        failures.append(f"Workout Timestamp contains time-of-day at rows {full_ts_rows[:5]}")

    ignored_status = git_output(repo, "status", "--short", "--ignored=matching", "raw_data/workouts_raw.csv")
    tracked_raw = git_output(repo, "ls-files", "raw_data/workouts_raw.csv")
    if tracked_raw:
        failures.append("raw_data/workouts_raw.csv is tracked")

    latest_heatmap_date = max(day["date"] for day in data["volume"]["heatmap"])
    visible = {
        "data_through_label": format_long_date(latest_heatmap_date),
        "headline_active_weeks": display_int(data["headline"]["longest_week_streak"]),
        "headline_core_workouts": display_int(data["headline"]["total_workouts"]),
        "headline_performance_rides": display_int(data["headline"]["performance_rides"]),
        "headline_training_hours": display_int(data["headline"]["total_hours"]),
        "volume_training_hours": display_int(data["volume"]["totals"]["hours"]),
        "volume_reported_miles": display_int(data["volume"]["totals"]["miles"]),
        "volume_estimated_calories": compact_calories(data["volume"]["totals"]["calories"]),
        "volume_core_workouts": display_int(data["volume"]["totals"]["workouts"]),
        "volume_ancillary_footnote": f"+{display_int(data['volume']['totals']['ancillary_workouts'])} warmups and cooldowns",
        "around_world_display": f"{data['volume']['totals']['around_world_x']:.1f}x around the Earth",
        "top_instructor": data["instructors"][0]["name"] if data["instructors"] else "",
        "top_instructor_count": display_int(data["instructors"][0]["count"]) if data["instructors"] else "",
    }

    print("# Peloton Dashboard QA")
    print()
    print(f"Repo: {repo}")
    print(f"CSV rows: {len(rows):,}")
    if rows:
        print(f"Date range: {rows[0]['Workout Timestamp']} -> {rows[-1]['Workout Timestamp']}")
    print(f"Raw export status: {ignored_status or '(not present)'}")
    print(f"Raw export tracked: {'YES' if tracked_raw else 'NO'}")
    print()
    print("## CSV vs JSON")
    print("| key | csv | json | status |")
    print("|---|---:|---:|---|")
    for key, csv_value, json_value, status in rows_out:
        print(f"| `{key}` | {csv_value} | {json_value} | {status} |")
    print()
    print("## Expected Visible Totals")
    for key, value in visible.items():
        print(f"- `{key}`: {value}")
    print()
    if failures:
        print("## FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("## PASS")
    print("- Embedded HTML DATA matches JSON.")
    print("- CSV recompute matches generated JSON.")
    print("- Raw export is not tracked.")
    print("- Scrubbed CSV has no Class Timestamp and date-only workout timestamps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
