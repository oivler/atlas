from __future__ import annotations

import os
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.db import connect, db_path
from app import reads

app = FastAPI(title="Atlas API", version="0.1.0")

_origins = os.environ.get(
    "ATLAS_CORS",
    "https://oivler.com,https://www.oivler.com,http://localhost:5500,http://127.0.0.1:5500,null",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _payload(builder: Callable, *, empty_ok: bool = False) -> Any:
    path = db_path()
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"atlas.db missing at {path}. Run: python -m pipeline.run_cycle --init",
        )
    with connect(path) as conn:
        cur = conn.cursor()
        data = builder(cur)
    if data is None and not empty_ok:
        raise HTTPException(status_code=404, detail="not ready yet")
    return data


@app.get("/health")
def health():
    p = db_path()
    return {"ok": True, "db": str(p), "exists": p.exists()}


@app.get("/meta.json")
def meta():
    return _payload(lambda c: reads.build_meta(c, live=True))


@app.get("/stats.json")
def stats():
    return _payload(reads.build_stats)


@app.get("/rising.json")
def rising():
    return _payload(reads.build_rising)


@app.get("/rising_articles.json")
def rising_articles():
    return _payload(reads.build_rising_articles)


@app.get("/trends.json")
def trends():
    return _payload(reads.build_trends)


@app.get("/trend_articles.json")
def trend_articles():
    return _payload(reads.build_trend_articles)


@app.get("/graph.json")
def graph():
    return _payload(reads.build_graph)


@app.get("/geo.json")
def geo():
    return _payload(reads.build_geo)


@app.get("/geo_articles.json")
def geo_articles():
    return _payload(reads.build_geo_articles)


@app.get("/eval.json")
def eval_endpoint():
    return _payload(reads.build_eval)


@app.get("/term-top.json")
def term_top():
    data = _payload(reads.build_term_top, empty_ok=True)
    if data is None:
        raise HTTPException(status_code=404, detail="no trends yet")
    return data


@app.get("/stats")
def stats_alias():
    return stats()


@app.get("/topics/rising")
def rising_alias():
    return rising()


@app.get("/graph")
def graph_alias():
    return graph()


@app.get("/api/geo")
def geo_alias():
    return geo()


@app.get("/api/eval")
def eval_alias():
    return eval_endpoint()


@app.get("/")
def root():
    return {
        "service": "atlas",
        "docs": "/docs",
        "health": "/health",
        "contract": [
            "/meta.json",
            "/stats.json",
            "/trends.json",
            "/trend_articles.json",
            "/term-top.json",
            "/eval.json",
            "/geo.json",
            "/geo_articles.json",
        ],
    }


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
