"""Shared HTTP + geo helpers for source clients."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

log = logging.getLogger("ranking.sources")

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)


@retry(**_RETRY)
def request_json(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    raise_for_status: bool = True,
) -> Optional[Dict[str, Any]]:
    """Make a JSON request with retry. Returns parsed JSON, or None on 4xx that
    we choose not to retry (returns None instead of raising for 'no result')."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.request(method, url, headers=headers, params=params, json=json_body)
        if resp.status_code == 404:
            return None
        if 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
            log.warning("%s %s -> %s: %s", method, url, resp.status_code, resp.text[:200])
            return None
        if raise_for_status:
            resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return None


def get_json(url: str, **kw: Any) -> Optional[Dict[str, Any]]:
    return request_json("GET", url, **kw)


def post_json(url: str, **kw: Any) -> Optional[Dict[str, Any]]:
    return request_json("POST", url, **kw)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def domain_of(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    s = url.lower().strip()
    s = s.split("://", 1)[-1]
    s = s.split("/", 1)[0]
    s = s.split("?", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s or None
