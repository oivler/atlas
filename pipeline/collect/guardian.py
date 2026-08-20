from __future__ import annotations

import sqlite3

import feedparser

from pipeline.collect.base import mark_fetched, parse_dt, upsert_items

SOURCE = "guardian"
FEED = "https://www.theguardian.com/world/rss"


def collect(conn: sqlite3.Connection) -> int:
    parsed = feedparser.parse(FEED)
    rows = []
    for e in parsed.entries[:80]:
        rows.append(
            {
                "title": e.get("title"),
                "url": e.get("link"),
                "community": "guardian",
                "source": SOURCE,
                "score": 0,
                "created_at": parse_dt(
                    e.get("published") or e.get("updated")
                ),
            }
        )
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
