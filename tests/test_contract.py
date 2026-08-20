from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import connect, init_db
from app import reads
from app.main import app

FIXTURES = ROOT / "data" / "atlas"


LIVE_FILES = [
    "meta.json",
    "stats.json",
    "eval.json",
    "trends.json",
    "trend_articles.json",
    "term-top.json",
    "geo.json",
    "geo_articles.json",
]


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    db = tmp_path / "atlas.db"
    monkeypatch.setenv("ATLAS_DB", str(db))

    init_db(db)
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO source_state (key, last_fetched) VALUES ('source:hackernews', datetime('now'))"
        )
        conn.executemany(
            """
            INSERT INTO items (title, url, community, source, score, created_at, latitude, longitude, location)
            VALUES (?, ?, ?, ?, ?, datetime('now', ?), ?, ?, ?)
            """,
            [
                (
                    "Iran deal talks continue in Tehran",
                    "https://example.com/1",
                    "guardian",
                    "guardian",
                    10,
                    "-1 day",
                    35.69,
                    51.39,
                    "Iran",
                ),
                (
                    "Iran officials meet in Tehran again",
                    "https://example.com/2",
                    "nyt",
                    "news",
                    5,
                    "-2 day",
                    35.69,
                    51.39,
                    "Iran",
                ),
                (
                    "Trump speaks on trade in Washington",
                    "https://example.com/3",
                    "hackernews",
                    "hackernews",
                    100,
                    "-1 hour",
                    38.9,
                    -77.04,
                    "United States",
                ),
                (
                    "Trump and Europe discuss tariffs",
                    "https://example.com/4",
                    "bbc",
                    "news",
                    3,
                    "-3 day",
                    38.9,
                    -77.04,
                    "United States",
                ),
                (
                    "OpenAI releases new model",
                    "https://example.com/5",
                    "devto",
                    "devto",
                    20,
                    "-5 hour",
                    None,
                    None,
                    None,
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO term_trends (key, term, momentum, recent, total, last_seen)
            VALUES
              ('trump', 'Trump', 5.0, 2, 4, datetime('now')),
              ('iran', 'Iran', 4.0, 2, 3, datetime('now')),
              ('openai', 'OpenAI', 3.0, 1, 2, datetime('now'))
            """
        )
        conn.commit()
    return db


def test_fixture_files_exist():
    for name in LIVE_FILES:
        assert (FIXTURES / name).exists(), name


def _load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_fixture_top_level_keys_stable():
    meta = _load_fixture("meta.json")
    assert set(meta) >= {"live", "generated_at", "note", "source_repo"}

    stats = _load_fixture("stats.json")
    assert set(stats) >= {
        "items",
        "terms",
        "sources",
        "outlets",
        "outlet_names",
        "last_item_at",
    }

    trends = _load_fixture("trends.json")
    assert isinstance(trends, list) and trends
    assert set(trends[0]) >= {"term", "key", "momentum", "recent", "total", "last_seen"}

    geo = _load_fixture("geo.json")
    assert set(geo) >= {"generated_at", "now", "default_hours", "windows"}
    assert "168" in geo["windows"]
    pin = geo["windows"]["168"][0]
    assert set(pin) >= {"lat", "lon", "location", "count", "sample_title"}

    ev = _load_fixture("eval.json")
    assert set(ev) >= {
        "terms_total",
        "terms_spiked",
        "terms_with_lead",
        "median_lead_days",
        "max_lead_days",
        "top_leads",
    }


def test_builders_match_fixture_keys(seeded_db):
    with connect(seeded_db) as conn:
        cur = conn.cursor()
        meta = reads.build_meta(cur, live=True)
        stats = reads.build_stats(cur)
        trends = reads.build_trends(cur)
        geo = reads.build_geo(cur)
        ev = reads.build_eval(cur)
        term_top = reads.build_term_top(cur)

    assert meta["live"] is True
    assert set(meta) == set(_load_fixture("meta.json"))
    assert set(stats) == set(_load_fixture("stats.json"))
    assert trends and set(trends[0]) == set(_load_fixture("trends.json")[0])
    assert set(geo) == set(_load_fixture("geo.json"))
    assert set(ev) == set(_load_fixture("eval.json"))
    assert term_top and set(term_top) >= {"term", "history"}
    assert stats["items"] == 5
    assert "Iran" in {p["location"] for p in geo["windows"]["8760"]}


def test_api_routes_registered():
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    for name in LIVE_FILES:
        assert f"/{name}" in paths
