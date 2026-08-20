from __future__ import annotations

import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from pipeline.collect.base import client, mark_fetched, parse_dt, upsert_items

SOURCE = "arxiv"
ATOM = "{http://www.w3.org/2005/Atom}"


def backfill(conn: sqlite3.Connection, *, days: int = 365) -> int:
    """Year of cs.AI / cs.LG / cs.CL papers, month by month."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    total = 0
    cursor = start
    with client() as http:
        while cursor < end:
            window_end = min(cursor + timedelta(days=30), end)
            q = (
                f"submittedDate:[{cursor.strftime('%Y%m%d')}000000"
                f" TO {window_end.strftime('%Y%m%d')}235959]"
                f" AND (cat:cs.AI OR cat:cs.LG OR cat:cs.CL)"
            )
            start_i = 0
            while start_i < 2000:
                try:
                    r = http.get(
                        "http://export.arxiv.org/api/query",
                        params={
                            "search_query": q,
                            "sortBy": "submittedDate",
                            "sortOrder": "descending",
                            "start": start_i,
                            "max_results": 100,
                        },
                    )
                    r.raise_for_status()
                    root = ET.fromstring(r.text)
                except Exception as e:
                    print(f"    arxiv {cursor.date()} fail: {e}")
                    break
                entries = root.findall(f"{ATOM}entry")
                if not entries:
                    break
                rows = []
                for entry in entries:
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
                total += upsert_items(conn, rows)
                start_i += len(entries)
                if len(entries) < 100:
                    break
                time.sleep(3.1)
            print(f"    arxiv through {window_end.date()} total_new={total}")
            cursor = window_end
            time.sleep(3.1)
    mark_fetched(conn, SOURCE)
    return total
