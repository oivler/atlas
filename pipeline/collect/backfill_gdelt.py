from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone

from pipeline.collect.base import client, community_from_url, mark_fetched, parse_dt, upsert_items
from pipeline.process.gazetteer import PLACES

SOURCE = "gdelt"

_COUNTRY = {}
for alias, lat, lon, canonical in PLACES:
    _COUNTRY[alias.lower()] = (canonical, lat, lon)


def _country_geo(name: str | None):
    if not name:
        return None
    hit = _COUNTRY.get(name.strip().lower())
    if hit:
        return hit
    for alias, lat, lon, canonical in PLACES:
        if alias.lower() == name.strip().lower():
            return canonical, lat, lon
    return None


def _parse_seen(seendate: str | None) -> str:
    if not seendate or len(seendate) < 14:
        return parse_dt(None)
    try:
        dt = datetime.strptime(seendate[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return parse_dt(None)


def backfill(conn: sqlite3.Connection, *, days: int = 365) -> int:
    """Year of English news via GDELT DOC API (daily windows, 250/day)."""
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    total = 0
    day = start
    with client() as http:
        while day < end:
            nxt = day + timedelta(days=1)
            params = {
                "query": "sourcelang:eng",
                "mode": "ArtList",
                "maxrecords": "250",
                "format": "json",
                "sort": "DateDesc",
                "startdatetime": day.strftime("%Y%m%d%H%M%S"),
                "enddatetime": nxt.strftime("%Y%m%d%H%M%S"),
            }
            try:
                r = http.get(
                    "https://api.gdeltproject.org/api/v2/doc/doc",
                    params=params,
                )
                if r.status_code != 200 or not r.content:
                    day = nxt
                    time.sleep(0.4)
                    continue
                data = r.json()
            except Exception as e:
                print(f"    gdelt {day.date()} fail: {e}")
                day = nxt
                time.sleep(0.5)
                continue
            rows = []
            for a in data.get("articles") or []:
                url = a.get("url")
                title = a.get("title")
                if not url or not title:
                    continue
                geo = _country_geo(a.get("sourcecountry"))
                row = {
                    "title": title,
                    "url": url,
                    "community": community_from_url(url, "gdelt"),
                    "source": SOURCE,
                    "score": 0,
                    "created_at": _parse_seen(a.get("seendate")),
                }
                if geo:
                    loc, lat, lon = geo
                    row["location"] = loc
                    row["latitude"] = lat
                    row["longitude"] = lon
                rows.append(row)
            n = upsert_items(conn, rows)
            total += n
            if day.day == 1 or n:
                print(f"    gdelt {day.date()} +{n} total_new={total}")
            day = nxt
            time.sleep(0.12)
    mark_fetched(conn, SOURCE)
    return total
