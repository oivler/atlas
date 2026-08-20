from __future__ import annotations

import argparse
import time

from app.db import connect, db_path, init_db


def run(*, days: int = 365, skip_ner: bool = False, only: str | None = None) -> None:
    path = db_path()
    if not path.exists():
        print(f"init schema -> {path}")
        init_db(path)
    else:
        init_db(path)

    conn = connect(path)
    try:
        steps = []
        if only in (None, "hn"):
            steps.append(("hn", "pipeline.collect.backfill_hn"))
        if only in (None, "gdelt"):
            steps.append(("gdelt", "pipeline.collect.backfill_gdelt"))
        if only in (None, "arxiv"):
            steps.append(("arxiv", "pipeline.collect.backfill_arxiv"))

        for name, modpath in steps:
            import importlib

            t0 = time.time()
            mod = importlib.import_module(modpath)
            n = mod.backfill(conn, days=days)
            print(f"backfill {name:6s} +{n}  ({time.time()-t0:.0f}s)", flush=True)

        from pipeline.process.retention import prune_older_than

        pruned = prune_older_than(conn, days=days)
        print(f"prune           -{pruned}", flush=True)

        from pipeline.process.geo import geotag

        t0 = time.time()
        g = geotag(conn, limit=500000)
        print(f"geotag          {g}  ({time.time()-t0:.0f}s)", flush=True)

        if not skip_ner:
            from pipeline.process.ner_trends import refresh_trends

            t0 = time.time()
            terms = refresh_trends(conn, lookback_days=min(days, 365), limit=200000)
            print(f"ner_trends      {terms}  ({time.time()-t0:.0f}s)", flush=True)

        items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        geo = conn.execute(
            "SELECT COUNT(*) FROM items WHERE latitude IS NOT NULL"
        ).fetchone()[0]
        print(f"done. items={items} geotagged={geo} db={path}", flush=True)
    finally:
        conn.close()


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--skip-ner", action="store_true")
    p.add_argument("--only", choices=["hn", "gdelt", "arxiv"], default=None)
    args = p.parse_args(argv)
    run(days=args.days, skip_ner=args.skip_ner, only=args.only)


if __name__ == "__main__":
    main()
