"""Stage 6 — emit the export artifact that the optional importer can push to a consuming app.

For each topic we write a JSON file plus one combined CSV under exports/<run_id>/.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Sequence

from . import config, db
from .slugs import nominee_slug


def _num(v: Any):
    return float(v) if v is not None else None


def run_export(topics: Sequence[Dict[str, Any]], run_id: str) -> None:
    out_dir = os.path.join(config.EXPORTS_DIR, run_id)
    os.makedirs(out_dir, exist_ok=True)
    combined: List[Dict[str, Any]] = []

    with db.connect() as conn:
        for t in topics:
            rows = db.ranking_for_topic(conn, t["slug"], run_id)
            records = []
            for r in rows:
                rec = {
                    "topic_slug": r["topic_slug"],
                    "rank_position": r["rank_position"],
                    "final_score": float(r["final_score"]),
                    "presence_score": float(r["final_score"]),
                    "name": r["name"],
                    "slug": nominee_slug(r["name"], r["place_id"]),
                    "place_id": r["place_id"],
                    "website": r["website"],
                    "address": r["address"],
                    "lat": _num(r["lat"]),
                    "lng": _num(r["lng"]),
                    "phone": r["phone"],
                    "photo_url": r["photo_url"],
                    "rating": _num(r["rating"]),
                    "rating_count": int(r["rating_count"]) if r["rating_count"] is not None else None,
                    "strengths": r["strengths"] or [],
                    "pillar_breakdown": r["pillar_breakdown"],
                }
                records.append(rec)
                combined.append(rec)
            with open(os.path.join(out_dir, "%s.json" % t["slug"]), "w", encoding="utf-8") as fh:
                json.dump({"run_id": run_id, "topic_slug": t["slug"], "rankings": records},
                          fh, ensure_ascii=False, indent=2)
            print("  export %-45s %3d rows" % (t["slug"], len(records)))

    if combined:
        csv_path = os.path.join(out_dir, "rankings.csv")
        fields = ["topic_slug", "rank_position", "final_score", "presence_score",
                  "name", "slug", "place_id", "website", "address", "lat", "lng",
                  "phone", "photo_url", "rating", "rating_count", "strengths"]
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for rec in combined:
                row = {**rec, "strengths": json.dumps(rec.get("strengths") or [], ensure_ascii=False)}
                w.writerow(row)
        print("  export wrote %s (%d total rows)" % (csv_path, len(combined)))
