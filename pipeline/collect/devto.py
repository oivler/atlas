from __future__ import annotations

import sqlite3

from pipeline.collect.base import client, mark_fetched, parse_dt, upsert_items

SOURCE = "devto"


def collect(conn: sqlite3.Connection, *, limit: int = 40) -> int:
    rows = []
    with client() as http:
        data = http.get(
            "https://dev.to/api/articles",
            params={"top": 1, "per_page": limit},
        ).json()
        for a in data or []:
            rows.append(
                {
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "community": "devto",
                    "source": SOURCE,
                    "score": a.get("positive_reactions_count") or 0,
                    "created_at": parse_dt(a.get("published_at")),
                }
            )
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
