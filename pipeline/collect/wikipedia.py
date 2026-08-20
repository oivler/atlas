from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from pipeline.collect.base import client, mark_fetched, upsert_items

SOURCE = "wikipedia"


def collect(conn: sqlite3.Connection) -> int:
    rows = []
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    with client() as http:
        r = http.get(f"https://en.wikipedia.org/api/rest_v1/feed/featured/{day}")
        if r.status_code != 200:
            mark_fetched(conn, SOURCE)
            return 0
        for block in (r.json().get("news") or [])[:20]:
            links = block.get("links") or []
            title = None
            url = None
            if links:
                link0 = links[0]
                title = link0.get("normalizedtitle") or (
                    (link0.get("titles") or {}).get("normalized")
                )
                url = (
                    (link0.get("content_urls") or {})
                    .get("desktop", {})
                    .get("page")
                )
                if not url:
                    page = (link0.get("titles") or {}).get("canonical")
                    if page:
                        url = f"https://en.wikipedia.org/wiki/{page}"
            if not title:
                title = re.sub(r"<[^>]+>", "", block.get("story") or "")[:200]
            if title and url:
                rows.append(
                    {
                        "title": title,
                        "url": url,
                        "community": "wikipedia",
                        "source": SOURCE,
                        "score": 0,
                        "created_at": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    }
                )
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
