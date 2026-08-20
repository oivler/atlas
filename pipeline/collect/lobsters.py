from __future__ import annotations

import sqlite3

from pipeline.collect.base import client, mark_fetched, parse_dt, upsert_items

SOURCE = "lobsters"


def collect(conn: sqlite3.Connection) -> int:
    rows = []
    with client() as http:
        data = http.get("https://lobste.rs/hottest.json").json()
        for s in data or []:
            rows.append(
                {
                    "title": s.get("title"),
                    "url": s.get("url") or s.get("comments_url"),
                    "community": "lobsters",
                    "source": SOURCE,
                    "score": s.get("score") or 0,
                    "created_at": parse_dt(s.get("created_at")),
                }
            )
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
