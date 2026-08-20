from __future__ import annotations

import re
import sqlite3

from pipeline.process.gazetteer import PLACES


def _find_place(title: str) -> tuple[str, float, float] | None:
    if not title:
        return None
    for alias, lat, lon, canonical in PLACES:

        pat = re.compile(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", re.I)
        if pat.search(title):
            return canonical, lat, lon
    return None


def geotag(conn: sqlite3.Connection, *, limit: int = 5000) -> int:
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT id, title FROM items
        WHERE location IS NULL
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    n = 0
    for iid, title in rows:
        hit = _find_place(title or "")
        if not hit:
            continue
        loc, lat, lon = hit
        cur.execute(
            "UPDATE items SET location=?, latitude=?, longitude=? WHERE id=?",
            (loc, lat, lon, iid),
        )
        n += 1
    conn.commit()
    return n
