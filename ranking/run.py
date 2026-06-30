"""CLI orchestrator for the ranking pipeline.

    python -m ranking.run --stage all
    python -m ranking.run --stage discover --topics best-coffee-downtown-toronto --limit 25
    python -m ranking.run --stage catalog --curate

Each run has a run_id (default: current month, YYYY-MM). Stages are idempotent, so
re-running the same run_id resumes/updates in place.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional, Sequence

logging.basicConfig(level=logging.WARNING, format="  ! %(name)s: %(message)s")

STAGES = ["catalog", "discover", "collect", "transform", "score", "strengths", "photos", "export"]


def _resolve_topics(only: Optional[Sequence[str]]) -> List[Dict[str, Any]]:
    """Topic dicts (with region centroid) from the DWH for the requested slugs."""
    from . import db

    with db.connect() as conn:
        return db.included_topics(conn, only)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="ranking.run", description="Local ranking pipeline")
    ap.add_argument("--stage", required=True, choices=STAGES + ["all"])
    ap.add_argument("--topics", help="comma-separated topic slugs (default: all included)")
    ap.add_argument("--run-id", help="batch id (default: current month YYYY-MM)")
    ap.add_argument("--limit", type=int, default=25, help="max businesses per topic in discover")
    ap.add_argument("--curate", action="store_true", help="catalog: also nominate hot pairs via LLM")
    args = ap.parse_args(argv)

    from . import db

    run_id = args.run_id or db.default_run_id()
    only = [s.strip() for s in args.topics.split(",")] if args.topics else None
    stages = STAGES if args.stage == "all" else [args.stage]

    print("== ranking run_id=%s stages=%s ==" % (run_id, ",".join(stages)))

    for stage in stages:
        print("[%s]" % stage)
        if stage == "catalog":
            from .catalog import run_catalog
            run_catalog(run_id, curate=args.curate)
            continue

        topics = _resolve_topics(only)
        if not topics:
            print("  no topics found — run `--stage catalog` first (or check --topics).")
            if args.stage != "all":
                return 1
            continue

        if stage == "discover":
            from .discover import run_discover
            run_discover(topics, run_id, limit=args.limit)
        elif stage == "collect":
            from .collect import run_collect
            run_collect(topics, run_id)
        elif stage == "transform":
            from .transform import run_transform
            run_transform([t["slug"] for t in topics], run_id)
        elif stage == "score":
            from .score import run_score
            run_score([t["slug"] for t in topics], run_id)
        elif stage == "strengths":
            from .strengths import run_strengths
            run_strengths([t["slug"] for t in topics], run_id)
        elif stage == "photos":
            from .photos import run_photos
            run_photos([t["slug"] for t in topics], run_id)
        elif stage == "export":
            from .export import run_export
            run_export(topics, run_id)

    with db.connect() as conn:
        db.finish_run(conn, run_id)
    print("== done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
