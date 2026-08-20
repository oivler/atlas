from __future__ import annotations

import sqlite3

import feedparser

from pipeline.collect.base import mark_fetched, parse_dt, upsert_items
from pipeline.collect.feeds import NEWS_FEEDS

SOURCE = "news"


def collect(conn: sqlite3.Connection, *, per_feed: int = 25) -> int:
    rows = []
    for community, url in NEWS_FEEDS:
        try:
            parsed = feedparser.parse(url)
        except Exception:
            continue
        for e in (parsed.entries or [])[:per_feed]:
            rows.append(
                {
                    "title": e.get("title"),
                    "url": e.get("link"),
                    "community": community,
                    "source": SOURCE,
                    "score": 0,
                    "created_at": parse_dt(e.get("published") or e.get("updated")),
                }
            )
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
