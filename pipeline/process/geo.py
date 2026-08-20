from __future__ import annotations

import re
import sqlite3

from pipeline.process.gazetteer import PLACES, US_CAPITAL, US_PLACES


def _match_alias(title: str, alias: str) -> bool:
    if len(alias) == 2 and alias.isalpha():
        return bool(re.search(rf",\s*{re.escape(alias)}\b", title, re.I))
    pat = re.compile(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", re.I)
    return bool(pat.search(title))


def find_place(title: str) -> tuple[str, float, float] | None:
    if not title:
        return None
    for alias, lat, lon, canonical in US_PLACES:
        if _match_alias(title, alias):
            return canonical, lat, lon
    for alias, lat, lon, canonical in PLACES:
        if _match_alias(title, alias):
            if canonical == "United States":
                return US_CAPITAL
            return canonical, lat, lon
    return None


def geotag(conn: sqlite3.Connection, *, limit: int = 5000, retag_us: bool = True) -> int:
    cur = conn.cursor()
    if retag_us:
        rows = cur.execute(
            """
            SELECT id, title, location FROM items
            WHERE location IS NULL
               OR location = 'United States'
               OR location = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (US_CAPITAL[0], limit),
        ).fetchall()
    else:
        rows = cur.execute(
            """
            SELECT id, title, location FROM items
            WHERE location IS NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    n = 0
    for iid, title, prev in rows:
        hit = find_place(title or "")
        if not hit and prev in ("United States", US_CAPITAL[0]):
            hit = US_CAPITAL
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
