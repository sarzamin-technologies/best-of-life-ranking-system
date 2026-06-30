"""Stage 2 — find candidate businesses for each topic×neighbourhood pair.

Entities come from Google Places (text + nearby), Yelp search, and the LLM's
"best X in <hood>" recommendations (resolved to a Google place so they merge on
place_id). Candidates are deduped, geo-filtered to the neighbourhood, and written
to `businesses` + `business_topics`. Web-search SERP and Reddit are NOT used to
create entities here (too noisy) — they feed signals later, in collect.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from . import db, place_types
from .config import SourceKeys
from .sources import google_places, yelp, ai_search
from .sources._http import domain_of, haversine_m


def _resolve_place_id(keys: SourceKeys, c: Dict[str, Any], lat: Optional[float], lng: Optional[float]) -> None:
    """If a candidate lacks a Google place_id (Yelp/AI origin), try to find it so
    it merges with the Google entity on the place_id key."""
    if c.get("place_id") or not google_places.enabled(keys):
        return
    q = c["name"]
    if c.get("address"):
        q += ", " + c["address"]
    hits = google_places.search_text(keys, q, lat, lng, radius_m=3000, max_results=3)
    if hits:
        g = hits[0]
        c["place_id"] = g.get("place_id")
        c.setdefault("lat", g.get("lat"))
        c.setdefault("lng", g.get("lng"))
        c["website"] = c.get("website") or g.get("website")
        c["domain"] = c.get("domain") or domain_of(g.get("website"))


def _within(c: Dict[str, Any], lat: Optional[float], lng: Optional[float], radius_m: float) -> Optional[float]:
    """Distance to neighbourhood centroid; None if unknown (kept by default)."""
    if lat is None or lng is None or c.get("lat") is None or c.get("lng") is None:
        return None
    return haversine_m(lat, lng, c["lat"], c["lng"])


def run_discover(topics: Sequence[Dict[str, Any]], run_id: str, limit: int = 25) -> None:
    keys = SourceKeys()
    with db.connect() as conn:
        db.ensure_run(conn, run_id, "discover")
        conn.commit()
        for t in topics:
            # Resumable: a topic already discovered to this depth is skipped, so the
            # whole pipeline can be re-run after an interruption and just continue.
            if db.topic_business_count(conn, t["slug"], run_id) >= limit:
                print("  discover %-45s skipped (already at depth %d)" % (t["slug"], limit))
                continue
            db.reset_topic(conn, t["slug"], run_id)  # clean re-discover of this topic
            cands = _gather(keys, t)
            lat, lng = t.get("center_lat"), t.get("center_lng")
            radius = float(t.get("search_radius_m") or 4000) * 1.5
            target = place_types.target_types(t["title"], t.get("category"))
            food = place_types.is_food(t["title"], t.get("category"))
            terms = place_types.topic_terms(t["title"])

            # Dedup, preserving relevance order (Google returns text results ranked
            # by relevance; dict keeps first-seen position). Distance is a hard
            # filter, NOT a sort key — otherwise big nearby landmarks float up.
            seen: Dict[str, Dict[str, Any]] = {}
            for c in cands:
                # Type filter: drop candidates whose Google place-type doesn't fit the
                # topic (a museum/university/hospital/park is not a "coffee shop").
                if c.get("discovered_via", "").startswith("google") \
                        and not place_types.accept(c.get("category"), target, food,
                                                   c.get("name", ""), terms):
                    continue
                _resolve_place_id(keys, c, lat, lng)
                dist = _within(c, lat, lng, radius)
                if dist is not None and dist > radius:
                    continue  # outside the neighbourhood
                c["distance_m"] = dist
                key = c.get("place_id") or (c.get("name", "").lower() + "|" + (c.get("address") or "")[:12].lower())
                if key not in seen:
                    seen[key] = c
                else:
                    # Same business from another source — merge its identifiers
                    # (e.g. a Yelp candidate resolved to this Google place brings a
                    # yelp_id) onto the first-seen record, keeping relevance order.
                    ex = seen[key]
                    for f in ("place_id", "yelp_id", "website", "domain", "lat", "lng",
                              "address", "phone"):
                        if not ex.get(f) and c.get(f):
                            ex[f] = c[f]

            kept = list(seen.values())[:limit]
            for c in kept:
                bid = db.upsert_business(conn, c, run_id)
                db.link_business_topic(conn, bid, t["slug"], run_id,
                                       c.get("discovered_via", "google_places"),
                                       c.get("discovery_query"), c.get("distance_m"))
            conn.commit()  # per-topic: resumable across interruptions
            print("  discover %-45s %3d candidates -> %3d kept" % (t["slug"], len(cands), len(kept)))


def _gather(keys: SourceKeys, t: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect raw candidates from all enabled sources, in relevance order
    (Google text first). Type/distance filtering happens in run_discover."""
    region_name = t.get("region_name", "Toronto")
    lat, lng = t.get("center_lat"), t.get("center_lng")
    radius = int(t.get("search_radius_m") or 4000)
    query = t.get("search_query") or _query(t["title"], region_name)
    target = place_types.target_types(t["title"], t.get("category"))
    food = place_types.is_food(t["title"], t.get("category"))
    terms = place_types.topic_terms(t["title"])
    out: List[Dict[str, Any]] = []

    if google_places.enabled(keys):
        # Text search is query-relevant and relevance-ranked — add it first.
        for c in google_places.search_text(keys, query, lat, lng, radius_m=radius, max_results=20):
            c.update(discovered_via="google_places", discovery_query=query)
            out.append(c)
        # Nearby fills gaps, but only for on-topic place-types.
        if lat is not None and lng is not None:
            for c in google_places.search_nearby(keys, lat, lng, radius_m=radius, max_results=20):
                if not place_types.accept(c.get("category"), target, food, c.get("name", ""), terms):
                    continue
                c.update(discovered_via="google_nearby", discovery_query=query)
                out.append(c)

    if yelp.enabled(keys) and lat is not None and lng is not None:
        term = _term(t["title"])
        for c in yelp.search(keys, term, lat, lng, radius_m=radius, limit=20):
            c.update(discovery_query=term)
            out.append(c)

    if ai_search.enabled(keys):
        for name in ai_search.ask_recommendations(keys, t["title"], region_name):
            out.append({"name": name, "discovered_via": "ai_search", "discovery_query": t["title"]})

    return out


def _query(title: str, region_name: str) -> str:
    core = title
    for p in ("Best ", "best "):
        if core.startswith(p):
            core = core[len(p):]
    if " in " in core:
        core = core.rsplit(" in ", 1)[0]
    return "%s in %s, Ontario, Canada" % (core.strip(), region_name)


def _term(title: str) -> str:
    core = title
    for p in ("Best ", "best "):
        if core.startswith(p):
            core = core[len(p):]
    if " in " in core:
        core = core.rsplit(" in ", 1)[0]
    return core.strip()
