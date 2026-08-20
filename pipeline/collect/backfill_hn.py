from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone

from pipeline.collect.base import client, mark_fetched, parse_dt, upsert_items

SOURCE = "hackernews"


def backfill(conn: sqlite3.Connection, *, days: int = 365) -> int:
    """Pull a year of HN stories via Algolia, week by week."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    total = 0
    cursor = start
    with client() as http:
        while cursor < end:
            window_end = min(cursor + timedelta(days=7), end)
            t0 = int(cursor.timestamp())
            t1 = int(window_end.timestamp())
            page = 0
            while page < 50:
                try:
                    r = http.get(
                        "https://hn.algolia.com/api/v1/search_by_date",
                        params={
                            "tags": "story",
                            "hitsPerPage": 100,
                            "page": page,
                            "numericFilters": f"created_at_i>={t0},created_at_i<{t1}",
                        },
                    )
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    print(f"    hn week {cursor.date()} page {page} fail: {e}")
                    break
                hits = data.get("hits") or []
                if not hits:
                    break
                rows = []
                for h in hits:
                    rows.append(
                        {
                            "title": h.get("title"),
                            "url": h.get("url")
                            or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                            "community": "hackernews",
                            "source": SOURCE,
                            "score": h.get("points") or 0,
                            "created_at": parse_dt(h.get("created_at")),
                        }
                    )
                total += upsert_items(conn, rows)
                nb_pages = int(data.get("nbPages") or 0)
                page += 1
                if page >= nb_pages:
                    break
                time.sleep(0.15)
            print(f"    hn through {window_end.date()} total_new={total}")
            cursor = window_end
            time.sleep(0.2)
    mark_fetched(conn, SOURCE)
    return total
