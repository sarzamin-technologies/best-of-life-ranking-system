"""Stage 6 — fetch a representative image for every ranked business.

Runs over the full ranked set (not just the top few, which the old website
seed-photos endpoint was limited to), resolves a Google Place photo URL, and caches
it on `businesses.photo_url`. Idempotent: skips businesses that already have a photo,
so re-runs are cheap. Resilient + per-business commit.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from . import db
from .config import SourceKeys
from .sources import google_places

log = logging.getLogger("ranking.photos")


def run_photos(topics: Sequence[str], run_id: str) -> None:
    keys = SourceKeys()
    if not google_places.enabled(keys):
        print("  photos skipped: no Google key configured")
        return

    with db.connect() as conn:
        for topic in topics:
            ranked = db.ranking_for_topic(conn, topic, run_id)
            todo = [r for r in ranked if r.get("place_id") and not r.get("photo_url")]
            done = 0
            for r in todo:
                try:
                    uri = google_places.fetch_photo_url(keys, r["place_id"])
                    if uri:
                        db.set_photo(conn, r["business_id"], uri)
                        conn.commit()
                        done += 1
                except Exception as e:  # pragma: no cover - network
                    conn.rollback()
                    log.warning("photo %s (%s) failed: %s", r.get("business_id"), r.get("name"), str(e)[:140])
            print("  photos %-44s %3d fetched (%d already had one)"
                  % (topic, done, len(ranked) - len(todo)))
