from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "atlas.db"
SCHEMA = ROOT / "pipeline" / "schema.sql"


def db_path() -> Path:
    return Path(os.environ.get("ATLAS_DB", DEFAULT_DB))


def connect(path: Path | None = None, *, wal: bool = True) -> sqlite3.Connection:
    p = path or db_path()
    conn = sqlite3.connect(str(p), timeout=60)
    conn.row_factory = sqlite3.Row
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path | None = None) -> Path:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA.read_text(encoding="utf-8")
    with connect(p) as conn:
        conn.executescript(sql)
        conn.commit()
    return p
