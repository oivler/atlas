from __future__ import annotations

import argparse
import time
import traceback

from app.db import connect, db_path, init_db

COLLECTORS = [
    ("hackernews", "pipeline.collect.hackernews"),
    ("lobsters", "pipeline.collect.lobsters"),
    ("github", "pipeline.collect.github"),
    ("arxiv", "pipeline.collect.arxiv"),
    ("devto", "pipeline.collect.devto"),
    ("guardian", "pipeline.collect.guardian"),
    ("wikipedia", "pipeline.collect.wikipedia"),
    ("news", "pipeline.collect.news_rss"),
    ("gdelt", "pipeline.collect.gdelt_recent"),
]


def _run_collector(name: str, modpath: str, conn) -> int:
    import importlib

    mod = importlib.import_module(modpath)
    return int(mod.collect(conn) or 0)


def run(*, init: bool = False, skip_ner: bool = False) -> None:
    path = db_path()
    if init or not path.exists():
        print(f"init schema -> {path}")
        init_db(path)

    conn = connect(path)
    try:
        total_new = 0
        for name, modpath in COLLECTORS:
            t0 = time.time()
            try:
                n = _run_collector(name, modpath, conn)
                print(f"  collect {name:12s} +{n:4d}  ({time.time()-t0:.1f}s)")
                total_new += n
            except Exception as e:
                print(f"  collect {name:12s} FAIL: {e}")
                traceback.print_exc(limit=1)

        from pipeline.process.retention import prune_older_than

        t0 = time.time()
        pruned = prune_older_than(conn, days=365)
        print(f"  prune (>365d)       -{pruned:4d}  ({time.time()-t0:.1f}s)")

        from pipeline.process.geo import geotag

        t0 = time.time()
        g = geotag(conn)
        print(f"  geotag              {g:4d}  ({time.time()-t0:.1f}s)")

        if not skip_ner:
            from pipeline.process.ner_trends import refresh_trends

            t0 = time.time()
            terms = refresh_trends(conn)
            print(f"  ner_trends          {terms:4d}  ({time.time()-t0:.1f}s)")
        else:
            print("  ner_trends          skipped")

        items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        print(f"done. items={items} new={total_new} db={path}")
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--init", action="store_true")
    p.add_argument("--skip-ner", action="store_true")
    args = p.parse_args(argv)
    run(init=args.init, skip_ner=args.skip_ner)


if __name__ == "__main__":
    main()
