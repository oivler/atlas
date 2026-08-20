from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from pipeline.collect.base import client, mark_fetched, parse_dt, upsert_items

SOURCE = "github"


def collect(conn: sqlite3.Connection, *, limit: int = 40) -> int:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = []
    with client() as http:
        r = http.get(
            "https://api.github.com/search/repositories",
            params={
                "q": f"created:>{since} stars:>20",
                "sort": "stars",
                "order": "desc",
                "per_page": min(limit, 50),
            },
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code == 403:

            mark_fetched(conn, SOURCE)
            return 0
        r.raise_for_status()
        for repo in (r.json().get("items") or [])[:limit]:
            rows.append(
                {
                    "title": f"{repo.get('full_name')}: {repo.get('description') or 'GitHub repository'}",
                    "url": repo.get("html_url"),
                    "community": "github",
                    "source": SOURCE,
                    "score": repo.get("stargazers_count") or 0,
                    "created_at": parse_dt(repo.get("created_at")),
                }
            )
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
