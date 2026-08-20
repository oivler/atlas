from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET

from pipeline.collect.base import client, mark_fetched, parse_dt, upsert_items

SOURCE = "arxiv"
ATOM = "{http://www.w3.org/2005/Atom}"


def collect(conn: sqlite3.Connection, *, limit: int = 50) -> int:
    rows = []
    with client() as http:
        r = http.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": limit,
            },
        )
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for entry in root.findall(f"{ATOM}entry"):
            title = (entry.findtext(f"{ATOM}title") or "").replace("\n", " ").strip()
            link = entry.findtext(f"{ATOM}id")
            published = entry.findtext(f"{ATOM}published")
            rows.append(
                {
                    "title": title,
                    "url": link,
                    "community": "arxiv",
                    "source": SOURCE,
                    "score": 0,
                    "created_at": parse_dt(published),
                }
            )
    n = upsert_items(conn, rows)
    mark_fetched(conn, SOURCE)
    return n
