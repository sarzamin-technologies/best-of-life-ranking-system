"""Reddit client — organic mentions/buzz for a business.

Uses the read-only OAuth "client credentials" flow (script app). We search
r/toronto and nearby subs for the business name and return matching posts/comments
so transform.py can compute a mention count + rough sentiment.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from ..config import SourceKeys
from ._http import _TIMEOUT

log = logging.getLogger("ranking.sources.reddit")

_TOKEN: Dict[str, Any] = {"value": None, "exp": 0.0}
_SUBREDDITS = "toronto+askTO+ontario+FoodToronto"


def enabled(keys: SourceKeys) -> bool:
    return bool(keys.reddit_client_id and keys.reddit_client_secret)


def _token(keys: SourceKeys) -> Optional[str]:
    now = time.time()
    if _TOKEN["value"] and _TOKEN["exp"] > now + 30:
        return _TOKEN["value"]
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(keys.reddit_client_id, keys.reddit_client_secret),
                data={"grant_type": "client_credentials", "scope": "read"},
                headers={"User-Agent": keys.reddit_user_agent},
            )
        resp.raise_for_status()
        j = resp.json()
        _TOKEN["value"] = j["access_token"]
        _TOKEN["exp"] = now + j.get("expires_in", 3600)
        return _TOKEN["value"]
    except Exception as e:  # pragma: no cover - network
        log.warning("reddit auth failed: %s", e)
        return None


def search_mentions(keys: SourceKeys, name: str, limit: int = 25) -> Dict[str, Any]:
    """Return {count, results:[{title, score, num_comments, url, created_utc}]}."""
    if not enabled(keys):
        return {"count": 0, "results": []}
    token = _token(keys)
    if not token:
        return {"count": 0, "results": []}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(
                "https://oauth.reddit.com/r/%s/search" % _SUBREDDITS,
                headers={"Authorization": "Bearer " + token, "User-Agent": keys.reddit_user_agent},
                params={"q": '"%s"' % name, "restrict_sr": "true", "limit": limit, "sort": "relevance"},
            )
        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
    except Exception as e:  # pragma: no cover - network
        log.warning("reddit search failed: %s", e)
        return {"count": 0, "results": []}

    results: List[Dict[str, Any]] = []
    for c in children:
        d = c.get("data", {})
        results.append({
            "title": d.get("title"),
            "score": d.get("score"),
            "num_comments": d.get("num_comments"),
            "url": "https://reddit.com" + (d.get("permalink") or ""),
            "created_utc": d.get("created_utc"),
        })
    return {"count": len(results), "results": results}
