"""Web search (SERP) client with a provider adapter: serpapi | brave | bing.

Two jobs:
  - discovery: pull business names mentioned on the SERP for "best X in <hood>"
  - visibility: where (if anywhere) a known business ranks for that query
We return the raw organic results; transform.py turns them into signals.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..config import SourceKeys
from ._http import get_json


def enabled(keys: SourceKeys) -> bool:
    return bool(keys.web_search)


def search(keys: SourceKeys, query: str, count: int = 20) -> List[Dict[str, Any]]:
    """Return a normalized list of organic results: {position, title, url, snippet}."""
    if not enabled(keys):
        return []
    provider = (keys.web_search_provider or "serpapi").lower()
    if provider == "serpapi":
        return _serpapi(keys, query, count)
    if provider == "brave":
        return _brave(keys, query, count)
    if provider == "bing":
        return _bing(keys, query, count)
    return []


def _serpapi(keys: SourceKeys, query: str, count: int) -> List[Dict[str, Any]]:
    j = get_json(
        "https://serpapi.com/search.json",
        params={"q": query, "num": count, "engine": "google", "gl": "ca", "hl": "en", "api_key": keys.web_search},
    )
    out = []
    for i, r in enumerate((j or {}).get("organic_results", []), start=1):
        out.append({"position": r.get("position", i), "title": r.get("title"),
                    "url": r.get("link"), "snippet": r.get("snippet")})
    return out


def _brave(keys: SourceKeys, query: str, count: int) -> List[Dict[str, Any]]:
    j = get_json(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": keys.web_search, "Accept": "application/json"},
        params={"q": query, "count": count, "country": "ca"},
    )
    out = []
    for i, r in enumerate(((j or {}).get("web") or {}).get("results", []), start=1):
        out.append({"position": i, "title": r.get("title"), "url": r.get("url"),
                    "snippet": r.get("description")})
    return out


def _bing(keys: SourceKeys, query: str, count: int) -> List[Dict[str, Any]]:
    j = get_json(
        "https://api.bing.microsoft.com/v7.0/search",
        headers={"Ocp-Apim-Subscription-Key": keys.web_search},
        params={"q": query, "count": count, "mkt": "en-CA"},
    )
    out = []
    for i, r in enumerate(((j or {}).get("webPages") or {}).get("value", []), start=1):
        out.append({"position": i, "title": r.get("name"), "url": r.get("url"),
                    "snippet": r.get("snippet")})
    return out
