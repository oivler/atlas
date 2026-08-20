from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone


KEEP_LABELS = {"PERSON", "ORG", "GPE", "EVENT", "PRODUCT", "WORK_OF_ART", "FAC"}

STOP_TERMS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "in",
    "on",
    "for",
    "to",
    "new",
    "old",
    "first",
    "second",
    "us",
    "u.s.",
    "uk",
    "eu",
    "un",
    "ai",
    "ceo",
    "inc",
    "ltd",
    "co",
    "corp",
    "today",
    "yesterday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy

        try:
            _nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
        except OSError as e:
            raise SystemExit(
                "spaCy model missing. Run: python -m spacy download en_core_web_sm"
            ) from e
    return _nlp


def _slug(term: str) -> str:
    s = term.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "term"


def _ok_term(term: str) -> bool:
    t = term.strip()
    if len(t) < 3 or len(t) > 60:
        return False
    if t.lower() in STOP_TERMS:
        return False
    if t.isdigit():
        return False

    if not re.search(r"[A-Za-z]", t):
        return False
    return True


def refresh_trends(conn: sqlite3.Connection, *, lookback_days: int = 21, limit: int = 8000) -> int:
    nlp = _get_nlp()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT title, created_at FROM items
        WHERE created_at >= datetime('now', ?)
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (f"-{lookback_days} days", limit),
    ).fetchall()


    hits: dict[str, list[str]] = defaultdict(list)
    display: dict[str, str] = {}

    texts = [(t or "", ca) for t, ca in rows if t]

    docs = nlp.pipe((t for t, _ in texts), batch_size=64)
    for (title, ca), doc in zip(texts, docs):
        seen_in_doc = set()
        for ent in doc.ents:
            if ent.label_ not in KEEP_LABELS:
                continue
            term = ent.text.strip()
            if not _ok_term(term):
                continue
            key = _slug(term)
            if not key or key in seen_in_doc:
                continue
            seen_in_doc.add(key)
            hits[key].append(ca)

            prev = display.get(key)
            if prev is None or (term[:1].isupper() and len(term) >= len(prev)):
                display[key] = term

    now = datetime.now(timezone.utc)
    recent_cut = now.timestamp() - 7 * 86400

    def _ts(ca: str) -> float:
        try:
            return datetime.strptime(ca[:19], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            ).timestamp()
        except ValueError:
            return now.timestamp()

    cur.execute("DELETE FROM term_trends")
    written = 0
    for key, stamps in hits.items():
        total = len(stamps)
        if total < 2:
            continue
        recent = sum(1 for s in stamps if _ts(s) >= recent_cut)
        older = max(1, total - recent)

        older_weeks = max(1.0, (lookback_days - 7) / 7.0)
        baseline = older / older_weeks
        momentum = recent / max(1.0, baseline)
        last_seen = max(stamps)
        cur.execute(
            """
            INSERT INTO term_trends (key, term, momentum, recent, total, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key, display.get(key, key), round(momentum, 3), recent, total, last_seen),
        )
        written += 1
    conn.commit()
    return written
