from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from pipeline.collect.backfill_gdelt import SOURCE, _article_geo, _parse_seen
from pipeline.collect.base import client, community_from_url, mark_fetched, upsert_items


def collect(conn: sqlite3.Connection) -> int:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=36)
    rows = []
    with client() as http:
        r = http.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": "sourcelang:eng",
                "mode": "ArtList",
                "maxrecords": "250",
                "format": "json",
                "sort": "DateDesc",
                "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                "enddatetime": end.strftime("%Y%m%d%H%M%S"),
            },
        )
        if r.status_code != 200 or not r.content:
            mark_fetched(conn, SOURCE)
            return 0
        for a in (r.json().get("articles") or []):
            url = a.get("url")
            title = a.get("title")
            if not url or not title:
                continue
            geo = _article_geo(title, a.get("sourcecountry"))
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
    mark_fetched(conn, SOURCE)
    return n
