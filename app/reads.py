from __future__ import annotations

import itertools
import json
import sqlite3
import statistics as _st
from datetime import date as _date
from datetime import timedelta as _td
from typing import Any

WINDOWS = [1, 24, 168, 720, 8760]
GEO_CAP = 250
ART_PER_LOC = 12

SOURCE_LABELS = {
    "hackernews": "Hacker News",
    "lobsters": "Lobsters",
    "github": "GitHub",
    "devto": "Dev.to",
    "arxiv": "arXiv",
    "news": "News RSS",
    "guardian": "The Guardian",
    "gdelt": "GDELT",
    "wikipedia": "Wikipedia Current Events",
    "reddit": "Reddit",
}


def to_iso(s: Any) -> str | None:
    if not s:
        return None
    s = str(s).split(".")[0].replace(" ", "T")
    return s + "Z"


def _dedup(rows, term_idx: int = 0):
    kept, low = [], []
    for r in rows:
        t = (r[term_idx] or "").lower()
        if any(t.startswith(k) or k.startswith(t) for k in low):
            continue
        kept.append(r)
        low.append(t)
    return kept


def _generated_at(cur: sqlite3.Cursor) -> str | None:
    gen = cur.execute(
        "SELECT MAX(last_fetched) FROM source_state WHERE key LIKE 'source:%'"
    ).fetchone()[0]
    if not gen:
        gen = cur.execute("SELECT MAX(created_at) FROM items").fetchone()[0]
    return gen


def _table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    row = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def build_meta(cur: sqlite3.Cursor, *, live: bool = True) -> dict:
    gen = _generated_at(cur)
    return {
        "live": live,
        "generated_at": to_iso(gen),
        "note": (
            "Live Atlas API (reads atlas.db)."
            if live
            else "Snapshot exported from atlas.db (scripts/export_atlas.py)."
        ),
        "source_repo": "oivler/atlas",
    }


def build_stats(cur: sqlite3.Cursor) -> dict:
    gen = _generated_at(cur)
    sources = sorted(r[0] for r in cur.execute("SELECT DISTINCT source FROM items"))
    news_feeds = 0
    try:
        news_feeds = cur.execute(
            "SELECT COUNT(DISTINCT community) FROM items WHERE source='news' "
            "AND created_at > datetime('now','-14 day')"
        ).fetchone()[0]
    except sqlite3.Error:
        news_feeds = 0

    def _src_label(s: str) -> str:
        base = SOURCE_LABELS.get(s, s)
        return f"{base} ({news_feeds} feeds)" if s == "news" and news_feeds else base

    outlet_names = sorted((_src_label(s) for s in sources), key=str.lower)
    terms = 0
    if _table_exists(cur, "term_trends"):
        terms = cur.execute("SELECT COUNT(*) FROM term_trends").fetchone()[0]
    return {
        "items": cur.execute("SELECT COUNT(*) FROM items").fetchone()[0],
        "terms": terms,
        "sources": sources,
        "outlets": len(sources),
        "outlet_names": outlet_names,
        "last_item_at": to_iso(gen),
    }


def _latest_history(cur: sqlite3.Cursor) -> dict[int, tuple]:
    if not _table_exists(cur, "topic_history"):
        return {}
    out: dict[int, tuple] = {}
    for tid, e, v, nc in cur.execute(
        """
        WITH latest AS (
          SELECT topic_id, MAX(bucket_ts) mx FROM topic_history GROUP BY topic_id
        )
        SELECT h.topic_id, h.emergence, h.velocity, h.n_communities
        FROM topic_history h JOIN latest l
          ON l.topic_id=h.topic_id AND l.mx=h.bucket_ts
        """
    ):
        out[tid] = (e or 0.0, v or 0.0, nc or 0)
    return out


def build_rising(cur: sqlite3.Cursor) -> list:
    if not _table_exists(cur, "topics"):
        return []
    hist = _latest_history(cur)
    topics = {
        tid: (label, json.loads(kw or "[]"), size, status, to_iso(fs), to_iso(ls))
        for tid, label, kw, size, status, fs, ls in cur.execute(
            "SELECT id,label,keywords,size,status,first_seen_at,last_seen_at "
            "FROM topics WHERE status='active'"
        )
    }

    def summary(tid: int) -> dict:
        label, kw, size, status, fs, ls = topics[tid]
        e, v, nc = hist.get(tid, (0.0, 0.0, 0))
        return {
            "id": tid,
            "label": label,
            "keywords": kw[:6],
            "size": size,
            "status": status,
            "emergence": round(e, 2),
            "velocity": round(v, 2),
            "n_communities": nc,
            "first_seen_at": fs,
            "last_seen_at": ls,
        }

    ranked = sorted(topics, key=lambda t: hist.get(t, (0,))[0], reverse=True)
    return [summary(t) for t in ranked[:50]]


def build_rising_articles(cur: sqlite3.Cursor) -> dict:
    if not (_table_exists(cur, "topics") and _table_exists(cur, "item_topics")):
        return {}
    hist = _latest_history(cur)
    topics = {
        tid: None
        for (tid,) in cur.execute("SELECT id FROM topics WHERE status='active'")
    }
    ranked = sorted(topics, key=lambda t: hist.get(t, (0,))[0], reverse=True)
    rising_art: dict[str, list] = {}
    for tid in ranked[:14]:
        rising_art[str(tid)] = [
            {
                "title": t,
                "url": u,
                "community": (com or src),
                "score": sc,
                "created_at": to_iso(ca),
            }
            for t, u, com, src, sc, ca in cur.execute(
                "SELECT i.title, i.url, i.community, i.source, i.score, i.created_at "
                "FROM item_topics it JOIN items i ON i.id = it.item_id "
                "WHERE it.topic_id = ? ORDER BY it.similarity DESC LIMIT 10",
                (tid,),
            )
        ]
    return rising_art


def build_trends(cur: sqlite3.Cursor) -> list:
    if not _table_exists(cur, "term_trends"):
        return []
    trend_rows = _dedup(
        cur.execute(
            "SELECT term, key, momentum, recent, total, last_seen FROM term_trends "
            "ORDER BY momentum DESC LIMIT 40"
        ).fetchall()
    )[:25]
    return [
        {
            "term": term,
            "key": key,
            "momentum": round(m or 0, 2),
            "recent": rec,
            "total": tot,
            "last_seen": to_iso(ls),
        }
        for term, key, m, rec, tot, ls in trend_rows
    ]


def build_trend_articles(cur: sqlite3.Cursor) -> dict:
    if not _table_exists(cur, "term_trends"):
        return {}
    trend_rows = _dedup(
        cur.execute(
            "SELECT term, key, momentum, recent, total, last_seen FROM term_trends "
            "ORDER BY momentum DESC LIMIT 40"
        ).fetchall()
    )[:25]
    trend_art: dict[str, list] = {}
    for term, key, m, rec, tot, ls in trend_rows:
        trend_art[key] = [
            {
                "title": t,
                "url": u,
                "community": (com or src),
                "created_at": to_iso(ca),
            }
            for t, u, com, src, ca in cur.execute(
                "SELECT title, url, community, source, created_at FROM items "
                "WHERE title LIKE ? ORDER BY created_at DESC LIMIT 12",
                (f"%{term}%",),
            )
        ]
    return trend_art


def build_graph(cur: sqlite3.Cursor) -> dict:
    if not _table_exists(cur, "term_trends"):
        return {"nodes": [], "links": []}
    g_terms = _dedup(
        cur.execute(
            "SELECT term, key, momentum, total FROM term_trends ORDER BY total DESC LIMIT 70"
        ).fetchall()
    )[:45]
    g_low = {k: term.lower() for term, k, _, _ in g_terms}
    g_keys = list(g_low)
    titles = [
        (r[0] or "").lower()
        for r in cur.execute(
            "SELECT title FROM items WHERE created_at >= datetime('now','-21 days')"
        )
    ]
    pair: dict[tuple, int] = {}
    for ttl in titles:
        present = [k for k in g_keys if g_low[k] in ttl]
        for a, b in itertools.combinations(present, 2):
            key = (a, b) if a < b else (b, a)
            pair[key] = pair.get(key, 0) + 1
    g_nodes = [
        {"id": k, "label": term, "size": tot, "emergence": round(m or 0, 2)}
        for term, k, m, tot in g_terms
    ]
    g_links = sorted(
        [{"source": a, "target": b, "weight": w} for (a, b), w in pair.items() if w >= 2],
        key=lambda l: l["weight"],
        reverse=True,
    )[:120]
    return {"nodes": g_nodes, "links": g_links}


def build_geo(cur: sqlite3.Cursor) -> dict:
    gen = _generated_at(cur)
    windows: dict[str, list] = {}
    for h in WINDOWS:
        rows = cur.execute(
            f"""
            SELECT location, AVG(latitude), AVG(longitude), COUNT(*) c
            FROM items
            WHERE latitude IS NOT NULL AND location IS NOT NULL
              AND created_at >= datetime('now','-{h} hours')
            GROUP BY location ORDER BY c DESC LIMIT {GEO_CAP}
            """
        ).fetchall()
        sample: dict[str, tuple] = {}
        for loc, title, url in cur.execute(
            f"""
            SELECT i.location, i.title, i.url FROM items i
            JOIN (
              SELECT location, MAX(created_at) mx FROM items
              WHERE latitude IS NOT NULL AND created_at >= datetime('now','-{h} hours')
              GROUP BY location
            ) m ON i.location=m.location AND i.created_at=m.mx
            """
        ):
            sample.setdefault(loc, (title, url))
        windows[str(h)] = [
            {
                "lat": round(lat, 3),
                "lon": round(lon, 3),
                "location": loc,
                "count": cnt,
                "sample_title": sample.get(loc, (None, None))[0],
            }
            for loc, lat, lon, cnt in rows
        ]
    export_now = cur.execute("SELECT datetime('now')").fetchone()[0]
    return {
        "generated_at": to_iso(gen),
        "now": to_iso(export_now),
        "default_hours": 168,
        "windows": windows,
    }


def build_geo_articles(cur: sqlite3.Cursor) -> dict:
    geo = build_geo(cur)
    win_set = {c["location"] for w in geo["windows"].values() for c in w}
    art: dict[str, list] = {}
    for loc, t, u, ca, com, src in cur.execute(
        """
        SELECT location, title, url, created_at, community, source FROM (
          SELECT location, title, url, created_at, community, source,
                 ROW_NUMBER() OVER (PARTITION BY location ORDER BY created_at DESC) rn
          FROM items WHERE latitude IS NOT NULL AND location IS NOT NULL
        ) WHERE rn <= ? ORDER BY location, rn
        """,
        (ART_PER_LOC,),
    ):
        if loc in win_set:
            art.setdefault(loc, []).append(
                {
                    "title": t,
                    "url": u,
                    "created_at": to_iso(ca),
                    "community": (com or src),
                }
            )
    return art


def build_eval(cur: sqlite3.Cursor) -> dict:
    empty = {
        "terms_total": 0,
        "terms_spiked": 0,
        "terms_with_lead": 0,
        "median_lead_days": None,
        "max_lead_days": 0,
        "top_leads": [],
    }
    if not _table_exists(cur, "term_trends"):
        return empty

    RISE_DAYS = 28
    PERENNIAL_FRAC = 0.40
    ref = _date.fromisoformat(cur.execute("SELECT date('now')").fetchone()[0])
    rise_cutoff = ref - _td(days=RISE_DAYS)

    def _isoweek(dstr: str):
        y, w, _ = _date.fromisoformat(dstr).isocalendar()
        return (y, w)

    total_hist_weeks = (
        len(
            {
                _isoweek(r[0])
                for r in cur.execute(
                    "SELECT DISTINCT date(created_at) FROM items "
                    "WHERE created_at >= datetime('now','-365 days') "
                    "AND created_at < datetime('now', ?)",
                    (f"-{RISE_DAYS} days",),
                )
            }
        )
        or 1
    )

    e_terms = _dedup(
        cur.execute(
            "SELECT term FROM term_trends ORDER BY momentum DESC LIMIT 150"
        ).fetchall()
    )[:120]
    leads = []
    for (term,) in e_terms:
        days = cur.execute(
            "SELECT date(created_at) d, COUNT(*) c FROM items "
            "WHERE title LIKE ? AND created_at >= datetime('now','-365 days') "
            "GROUP BY d ORDER BY d",
            (f"%{term}%",),
        ).fetchall()
        recent = [(d, c) for d, c in days if _date.fromisoformat(d) >= rise_cutoff]
        if len(recent) < 2:
            continue
        seen_weeks = {
            _isoweek(d) for d, _ in days if _date.fromisoformat(d) < rise_cutoff
        }
        if len(seen_weeks) / total_hist_weeks > PERENNIAL_FRAC:
            continue
        peak_i = max(range(len(recent)), key=lambda i: recent[i][1])
        peak_d = _date.fromisoformat(recent[peak_i][0])
        onset = next(
            (_date.fromisoformat(d) for d, c in recent if c >= 2),
            _date.fromisoformat(recent[0][0]),
        )
        leads.append((term, (peak_d - onset).days, recent[peak_i][1]))

    spiked = [l for l in leads if l[2] >= 4]
    positive = [l for l in spiked if l[1] >= 1]
    med = round(_st.median([l[1] for l in positive]), 1) if positive else None
    top_leads = sorted(positive, key=lambda l: l[1], reverse=True)[:6]
    return {
        "terms_total": len(leads),
        "terms_spiked": len(spiked),
        "terms_with_lead": len(positive),
        "median_lead_days": med,
        "max_lead_days": max([l[1] for l in positive], default=0),
        "top_leads": [{"term": t, "lead_days": ld} for t, ld, _ in top_leads],
    }


def build_term_top(cur: sqlite3.Cursor) -> dict | None:
    if not _table_exists(cur, "term_trends"):
        return None
    trend_rows = _dedup(
        cur.execute(
            "SELECT term, key, momentum, recent, total, last_seen FROM term_trends "
            "ORDER BY momentum DESC LIMIT 40"
        ).fetchall()
    )[:25]
    if not trend_rows:
        return None
    top_term = trend_rows[0][0]
    days = cur.execute(
        "SELECT date(created_at) d, COUNT(*) c FROM items "
        "WHERE title LIKE ? AND created_at >= datetime('now','-21 days') "
        "GROUP BY d ORDER BY d",
        (f"%{top_term}%",),
    ).fetchall()
    return {
        "term": top_term,
        "history": [
            {"bucket_ts": d + "T00:00:00Z", "emergence": c} for d, c in days
        ],
    }


BUILDERS = {
    "meta.json": lambda cur: build_meta(cur, live=True),
    "stats.json": build_stats,
    "rising.json": build_rising,
    "rising_articles.json": build_rising_articles,
    "trends.json": build_trends,
    "trend_articles.json": build_trend_articles,
    "graph.json": build_graph,
    "geo.json": build_geo,
    "geo_articles.json": build_geo_articles,
    "eval.json": build_eval,
    "term-top.json": build_term_top,
}


def build_all(cur: sqlite3.Cursor, *, live: bool = True) -> dict[str, Any]:
    out = {name: fn(cur) for name, fn in BUILDERS.items() if name != "meta.json"}
    out["meta.json"] = build_meta(cur, live=live)

    if out.get("term-top.json") is None:
        out.pop("term-top.json", None)
    return out
