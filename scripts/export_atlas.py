from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import connect, db_path
from app import reads

OUT = Path(os.environ.get("ATLAS_EXPORT_DIR", ROOT / "data" / "atlas"))


def write(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "topics").mkdir(parents=True, exist_ok=True)
    path = OUT / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  wrote {name:22s} ({path.stat().st_size // 1024 or 1} KB)")


def main() -> None:
    path = db_path()
    if not path.exists():
        sys.exit(f"atlas.db not found at {path}. Run: python -m pipeline.run_cycle --init")
    live = os.environ.get("ATLAS_EXPORT_LIVE", "").lower() in ("1", "true", "yes")
    with connect(path) as conn:
        cur = conn.cursor()
        payloads = reads.build_all(cur, live=live)
    for name, obj in payloads.items():
        if obj is None:
            continue
        write(name, obj)
    print("done.")


if __name__ == "__main__":
    main()
