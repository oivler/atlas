from __future__ import annotations

import sqlite3


def prune_older_than(conn: sqlite3.Connection, *, days: int = 365) -> int:
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM items WHERE created_at < datetime('now', ?)",
        (f"-{int(days)} days",),
    )
    deleted = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    conn.commit()
    return deleted
