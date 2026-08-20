from __future__ import annotations

import sqlite3

from pipeline.collect.base import client, mark_fetched, parse_dt, upsert_items

SOURCE = "hackernews"


def collect(conn: sqlite3.Connection, *, limit: int = 60) -> int:
    rows = []
    with client() as http:
        try:
            ids = http.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json"
            ).json()[:limit]
            for iid in ids:
                try:
                    item = http.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{iid}.json"
                    ).json()
                except Exception:
                    continue
                if not item or item.get("type") != "story":
                    continue
                title = item.get("title")
                url = item.get("url") or f"https://news.ycombinator.com/item?id={iid}"
                rows.append(
                    {
                        "title": title,
                        "url": url,
                        "community": "hackernews",
                        "source": SOURCE,
                        "score": item.get("score") or 0,
                        "created_at": parse_dt(item.get("time")),
                    }
                )
        except Exception:

            data = http.get(
                "https://hn.algolia.com/api/v1/search",
                params={"tags": "front_page", "hitsPerPage": limit},
            ).json()
            for h in data.get("hits") or []:
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
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
