#!/usr/bin/env python3
"""Draw weekly Strava distance totals for the last 52 weeks as an SVG bar chart.

Uses only the standard library. Reads STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET and
STRAVA_REFRESH_TOKEN from the environment. Only the date, sport type and distance of
each activity are kept; nothing else from the API response is used or stored.

    python3 strava_graph.py OUTPUT.svg                      # fetch from Strava
    python3 strava_graph.py OUTPUT.svg --input sample.json  # offline, for testing
"""

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from html import escape

WEEKS = 52
API = "https://www.strava.com/api/v3"

RUN = {"Run", "TrailRun", "VirtualRun"}
RIDE = {"Ride", "GravelRide", "MountainBikeRide", "EBikeRide", "EMountainBikeRide", "VirtualRide", "Velomobile"}
GROUPS = ["Run", "Ride", "Other"]


def group_of(sport_type: str) -> str:
    if sport_type in RUN:
        return "Run"
    if sport_type in RIDE:
        return "Ride"
    return "Other"


def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as resp:
        return json.load(resp)


def access_token() -> str:
    refresh_token = os.environ["STRAVA_REFRESH_TOKEN"]
    token = _post_form(
        "https://www.strava.com/oauth/token",
        {
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    if token.get("refresh_token") and token["refresh_token"] != refresh_token:
        print("::warning::Strava issued a new refresh token. Re-run scripts/setup_strava.py if this job starts failing.",
              file=sys.stderr)
    return token["access_token"]


def fetch_activities(after: dt.date) -> list[dict]:
    token = access_token()
    after_epoch = int(dt.datetime.combine(after, dt.time(), dt.timezone.utc).timestamp())
    activities, page = [], 1
    while True:
        query = urllib.parse.urlencode({"after": after_epoch, "per_page": 200, "page": page})
        req = urllib.request.Request(f"{API}/athlete/activities?{query}", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.load(resp)
        # Keep only what the chart needs; routes, names, heart rate etc. are dropped here.
        activities += [
            {
                "date": a["start_date_local"][:10],
                "type": a.get("sport_type") or a.get("type", ""),
                "km": (a.get("distance") or 0) / 1000,
            }
            for a in batch
        ]
        if len(batch) < 200:
            return activities
        page += 1


def weekly_totals(activities: list[dict], first_monday: dt.date) -> list[dict]:
    weeks = [{"start": first_monday + dt.timedelta(weeks=i), **{g: 0.0 for g in GROUPS}} for i in range(WEEKS)]
    for a in activities:
        day = dt.date.fromisoformat(a["date"])
        index = (day - first_monday).days // 7
        if 0 <= index < WEEKS:
            weeks[index][group_of(a["type"])] += a["km"]
    return weeks


def nice_ceiling(value: float) -> int:
    if value <= 0:
        return 10
    for step in (10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if value <= step * 4:
            return int(-(-value // step) * step)
    return int(-(-value // 1000) * 1000)


def render_svg(weeks: list[dict]) -> str:
    width, height = 820, 230
    left, right, top, bottom = 60, 12, 52, 28
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / WEEKS
    bar_w = slot * 0.72

    totals = [sum(w[g] for g in GROUPS) for w in weeks]
    y_max = nice_ceiling(max(totals))
    grand_total = sum(totals)
    active_weeks = sum(1 for t in totals if t > 0)

    def y(km: float) -> float:
        return top + plot_h - km / y_max * plot_h

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Weekly distance from Strava, last {WEEKS} weeks">',
        "<style>",
        "  :root { --text: #1f2328; --muted: #59636e; --grid: #d1d9e0; }",
        "  @media (prefers-color-scheme: dark) { :root { --text: #f0f6fc; --muted: #9198a1; --grid: #3d444d; } }",
        "  text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #59636e; fill: var(--muted); font-size: 11px; }",
        "  .title { fill: #1f2328; fill: var(--text); font-size: 14px; font-weight: 600; }",
        "  .grid { stroke: #d1d9e0; stroke: var(--grid); stroke-width: 1; }",
        "  .Run { fill: #fc4c02; } .Ride { fill: #3b82f6; } .Other { fill: #8b949e; }",
        "</style>",
        f'<text class="title" x="{left}" y="20">Weekly distance, last {WEEKS} weeks</text>',
        f'<text x="{left}" y="38">{grand_total:,.0f} km total · active {active_weeks} of {WEEKS} weeks</text>',
    ]

    legend_x = width - right
    for group in reversed(GROUPS):
        out.append(f'<text x="{legend_x}" y="20" text-anchor="end">{group}</text>')
        legend_x -= len(group) * 6.5 + 4
        out.append(f'<rect class="{group}" x="{legend_x - 10:.1f}" y="11" width="10" height="10" rx="2"/>')
        legend_x -= 24

    for tick in (0, y_max / 2, y_max):
        ty = y(tick)
        out.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{ty:.1f}" y2="{ty:.1f}"/>')
        label = f"{tick:g} km" if tick == y_max else f"{tick:g}"
        out.append(f'<text x="{left - 6}" y="{ty + 4:.1f}" text-anchor="end">{label}</text>')

    previous_month = None
    for i, week in enumerate(weeks):
        x = left + i * slot + (slot - bar_w) / 2
        base = 0.0
        tooltip = escape(f"Week of {week['start']:%d %b %Y}: " + ", ".join(
            f"{g} {week[g]:.1f} km" for g in GROUPS if week[g] > 0) if totals[i] else f"Week of {week['start']:%d %b %Y}: rest")
        out.append(f"<g><title>{tooltip}</title>")
        for group in GROUPS:
            km = week[group]
            if km <= 0:
                continue
            y_top, y_bottom = y(base + km), y(base)
            out.append(f'<rect class="{group}" x="{x:.1f}" y="{y_top:.1f}" width="{bar_w:.1f}" '
                       f'height="{max(y_bottom - y_top, 0.5):.1f}"/>')
            base += km
        out.append("</g>")

        month = week["start"].month
        if month != previous_month and i > 1:
            out.append(f'<text x="{left + i * slot:.1f}" y="{height - 8}">{week["start"]:%b}</text>')
        previous_month = month

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output")
    parser.add_argument("--input", help="JSON list of {date, type, km} instead of calling Strava")
    args = parser.parse_args()

    today = dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    first_monday = this_monday - dt.timedelta(weeks=WEEKS - 1)

    if args.input:
        with open(args.input) as f:
            activities = json.load(f)
    else:
        # One day of slack for time zones; weekly_totals() drops anything outside the range.
        activities = fetch_activities(first_monday - dt.timedelta(days=1))

    with open(args.output, "w") as f:
        f.write(render_svg(weekly_totals(activities, first_monday)))
    print(f"Wrote {args.output} from {len(activities)} activities")


if __name__ == "__main__":
    main()
