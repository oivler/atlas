from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

USER_AGENT = "AtlasBot/0.1 (+https://oivler.com/atlas.html; portfolio demo)"
TIMEOUT = 45.0


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(value: Any) -> str:
    if value is None:
        return utc_now()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    s = str(value).strip()
    if not s:
        return utc_now()
    s2 = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return utc_now()


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def community_from_url(url: str, fallback: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        host = re.sub(r"^www\.", "", host)
        return host.split(".")[0] if host else fallback
    except Exception:
        return fallback


def upsert_items(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    cur = conn.cursor()
    n = 0
    for r in rows:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        if not title or not url:
            continue
        try:
            cur.execute(
                """
                INSERT INTO items (
                  title, url, community, source, score, created_at,
                  latitude, longitude, location
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title[:500],
                    url[:1000],
                    (r.get("community") or "")[:120],
                    r["source"],
                    int(r.get("score") or 0),
                    r.get("created_at") or utc_now(),
                    r.get("latitude"),
                    r.get("longitude"),
                    (r.get("location") or None),
                ),
            )
            n += 1
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    return n


def mark_fetched(conn: sqlite3.Connection, source: str) -> None:
    conn.execute(
        """
        INSERT INTO source_state (key, last_fetched) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET last_fetched=excluded.last_fetched
        """,
        (f"source:{source}", utc_now()),
    )
    conn.commit()
