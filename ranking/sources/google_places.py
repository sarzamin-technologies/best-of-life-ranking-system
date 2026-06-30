"""Google Places API (New / v1) client.

Ported from src/lib/audit-sources/google-maps.server.ts. Calls the Google API
directly with GOOGLE_MAPS_API_KEY; if only a Lovable gateway key is present it
routes through the connector gateway instead (same field masks).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config import SourceKeys
from ._http import domain_of, post_json, get_json

_DIRECT = "https://places.googleapis.com/v1"
_GATEWAY = "https://connector-gateway.lovable.dev/google_maps/places/v1"

SEARCH_FIELDS = ",".join(
    "places." + f
    for f in [
        "id", "displayName", "formattedAddress", "location", "rating",
        "userRatingCount", "primaryType", "primaryTypeDisplayName",
        "websiteUri", "nationalPhoneNumber", "editorialSummary", "types",
    ]
)
DETAIL_FIELDS = ",".join(
    [
        "id", "displayName", "formattedAddress", "location", "rating",
        "userRatingCount", "primaryType", "primaryTypeDisplayName", "websiteUri",
        "internationalPhoneNumber", "regularOpeningHours", "types", "reviews",
    ]
)


def enabled(keys: SourceKeys) -> bool:
    return bool(keys.google_maps or keys.lovable)


def _base(keys: SourceKeys) -> str:
    return _DIRECT if keys.google_maps else _GATEWAY


def _headers(keys: SourceKeys, field_mask: str) -> Dict[str, str]:
    h = {"Content-Type": "application/json", "X-Goog-FieldMask": field_mask}
    if keys.google_maps:
        h["X-Goog-Api-Key"] = keys.google_maps
    else:  # gateway
        h["Authorization"] = "Bearer " + keys.lovable
    return h


def _to_candidate(p: Dict[str, Any]) -> Dict[str, Any]:
    name = (p.get("displayName") or {}).get("text") or p.get("name") or "Unknown"
    loc = p.get("location") or {}
    website = p.get("websiteUri")
    return {
        "place_id": p.get("id"),
        "name": name,
        "address": p.get("formattedAddress"),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "phone": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber"),
        "website": website,
        "domain": domain_of(website),
        "category": p.get("primaryType"),
    }


def search_text(
    keys: SourceKeys, query: str, lat: Optional[float] = None, lng: Optional[float] = None,
    radius_m: int = 5000, max_results: int = 20,
) -> List[Dict[str, Any]]:
    if not enabled(keys):
        return []
    body: Dict[str, Any] = {"textQuery": query, "pageSize": min(max_results, 20)}
    if lat is not None and lng is not None:
        body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}}
    j = post_json(_base(keys) + "/places:searchText", headers=_headers(keys, SEARCH_FIELDS), json_body=body)
    return [_to_candidate(p) for p in (j or {}).get("places", [])]


def search_nearby(
    keys: SourceKeys, lat: float, lng: float, included_type: Optional[str] = None,
    radius_m: int = 2000, max_results: int = 20,
) -> List[Dict[str, Any]]:
    if not enabled(keys):
        return []
    body: Dict[str, Any] = {
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_m}},
        "maxResultCount": min(max_results, 20),
    }
    if included_type:
        body["includedTypes"] = [included_type]
    j = post_json(_base(keys) + "/places:searchNearby", headers=_headers(keys, SEARCH_FIELDS), json_body=body)
    return [_to_candidate(p) for p in (j or {}).get("places", [])]


def place_details(keys: SourceKeys, place_id: str) -> Optional[Dict[str, Any]]:
    """Full details incl. up to 5 reviews + opening hours. Returns the raw payload."""
    if not enabled(keys) or not place_id:
        return None
    return get_json(_base(keys) + "/places/" + place_id, headers=_headers(keys, DETAIL_FIELDS))


def fetch_photo_url(keys: SourceKeys, place_id: str, max_height: int = 800) -> Optional[str]:
    """Resolve a usable image URL for a place: read its first photo reference, then
    the photo media endpoint (skipHttpRedirect returns the URL as JSON). Returns None
    if the place has no photo."""
    if not enabled(keys) or not place_id:
        return None
    det = get_json(_base(keys) + "/places/" + place_id, headers=_headers(keys, "photos"))
    photos = (det or {}).get("photos") or []
    name = photos[0].get("name") if photos else None
    if not name:
        return None
    # Media endpoint takes auth only (no field mask); skipHttpRedirect returns JSON.
    auth = {"X-Goog-Api-Key": keys.google_maps} if keys.google_maps \
        else {"Authorization": "Bearer " + keys.lovable}
    media = get_json(
        "%s/%s/media?maxHeightPx=%d&skipHttpRedirect=true" % (_base(keys), name, max_height),
        headers=auth,
    )
    return (media or {}).get("photoUri")
