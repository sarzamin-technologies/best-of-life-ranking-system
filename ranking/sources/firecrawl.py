"""Firecrawl website scrape -> SEO/quality signals + branding.

Ported from src/lib/audit-sources/website.server.ts and firecrawl-extras.server.ts.
We request markdown + html + metadata and derive the same quality flags the TS
audit used (schema.org, viewport, canonical, https, og, content depth).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ..config import SourceKeys
from ._http import post_json

_BASE = "https://api.firecrawl.dev/v2"


def enabled(keys: SourceKeys) -> bool:
    return bool(keys.firecrawl)


def scrape(keys: SourceKeys, url: str) -> Optional[Dict[str, Any]]:
    """Scrape a site and return a normalized audit dict (the raw payload)."""
    if not enabled(keys) or not url:
        return None
    if not re.match(r"^https?://", url):
        url = "https://" + url
    body = {
        "url": url,
        "formats": ["markdown", "html", "summary"],
        "onlyMainContent": False,
        "timeout": 12000,
    }
    # Firecrawl frequently times out (408) or rate-limits on slow sites — never let
    # that bubble up and abort the pipeline; a failed scrape just means no digital signal.
    try:
        j = post_json(_BASE + "/scrape", headers={"Authorization": "Bearer " + keys.firecrawl}, json_body=body)
    except Exception:
        return {"fetched": False, "url": url}
    if not j or not j.get("success"):
        return {"fetched": False, "url": url}
    return _audit(url, j.get("data", {}))


def _audit(url: str, data: Dict[str, Any]) -> Dict[str, Any]:
    html = data.get("html") or ""
    md = data.get("markdown") or ""
    meta = data.get("metadata") or {}
    low = html.lower()

    schema_types = re.findall(r'"@type"\s*:\s*"([^"]+)"', html)
    word_count = len(md.split())
    h1s = re.findall(r"<h1[\s>]", low)

    return {
        "fetched": True,
        "url": url,
        "title": meta.get("title"),
        "description": meta.get("description"),
        "summary": data.get("summary"),
        "h1_count": len(h1s),
        "word_count": word_count,
        "has_schema_org": bool(schema_types),
        "schema_types": sorted(set(schema_types)),
        "has_open_graph": 'property="og:' in low or "property='og:" in low,
        "has_viewport": 'name="viewport"' in low,
        "has_canonical": 'rel="canonical"' in low,
        "is_https": url.lower().startswith("https://"),
        "status": meta.get("statusCode"),
    }
