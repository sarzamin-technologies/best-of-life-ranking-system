"""Yelp Fusion API client — search + business details + reviews.

https://docs.developer.yelp.com/
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..config import SourceKeys
from ._http import domain_of, get_json

_BASE = "https://api.yelp.com/v3"


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(the|inc|ltd|co|cafe|coffee|bar|shop|restaurant|company)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    return len(ta & tb) >= max(1, min(len(ta), len(tb)) // 2)


def enabled(keys: SourceKeys) -> bool:
    return bool(keys.yelp)


def _headers(keys: SourceKeys) -> Dict[str, str]:
    return {"Authorization": "Bearer " + keys.yelp}


def _to_candidate(b: Dict[str, Any]) -> Dict[str, Any]:
    loc = b.get("coordinates") or {}
    addr = ", ".join((b.get("location") or {}).get("display_address") or [])
    cats = b.get("categories") or []
    return {
        "yelp_id": b.get("id"),
        "name": b.get("name"),
        "address": addr or None,
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "phone": b.get("phone"),
        "website": b.get("url"),  # yelp listing url; real site not exposed by Fusion
        "domain": domain_of(b.get("url")),
        "category": cats[0]["alias"] if cats else None,
        "discovered_via": "yelp",
    }


def search(
    keys: SourceKeys, term: str, lat: float, lng: float, radius_m: int = 4000, limit: int = 20,
) -> List[Dict[str, Any]]:
    if not enabled(keys):
        return []
    params = {
        "term": term,
        "latitude": lat,
        "longitude": lng,
        "radius": min(radius_m, 40000),
        "limit": min(limit, 50),
        "sort_by": "best_match",
    }
    j = get_json(_BASE + "/businesses/search", headers=_headers(keys), params=params)
    return [_to_candidate(b) for b in (j or {}).get("businesses", [])]


def match_business(keys: SourceKeys, name: str, lat: Optional[float], lng: Optional[float],
                   address: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a known business on Yelp via name search near its coordinates, so we
    get cross-platform ratings even when Yelp's category search surfaced different
    places. Returns the matching Yelp business dict (id, rating, review_count, ...)
    or None. Picks the most-reviewed name match to avoid stale/duplicate listings."""
    if not enabled(keys) or not name or lat is None or lng is None:
        return None
    j = get_json(_BASE + "/businesses/search", headers=_headers(keys),
                 params={"term": name, "latitude": lat, "longitude": lng,
                         "radius": 1000, "limit": 10, "sort_by": "best_match"})
    hits = [b for b in (j or {}).get("businesses", []) if _name_match(name, b.get("name", ""))]
    if not hits:
        return None
    return max(hits, key=lambda b: b.get("review_count") or 0)


def business(keys: SourceKeys, yelp_id: str) -> Optional[Dict[str, Any]]:
    if not enabled(keys) or not yelp_id:
        return None
    return get_json(_BASE + "/businesses/" + yelp_id, headers=_headers(keys))


def reviews(keys: SourceKeys, yelp_id: str) -> Dict[str, Any]:
    """Up to 3 review excerpts (Fusion limit) + total count."""
    if not enabled(keys) or not yelp_id:
        return {}
    return get_json(_BASE + "/businesses/" + yelp_id + "/reviews",
                    headers=_headers(keys), params={"limit": 20, "sort_by": "yelp_sort"}) or {}
