"""SEMrush Analytics API client — domain overview signals.

Ported from src/lib/audit-sources/semrush.server.ts. SEMrush returns ';'-delimited
CSV text, not JSON, so we parse manually. Used only for businesses that have a
real website domain.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from ..config import SourceKeys
from ._http import _TIMEOUT, domain_of

log = logging.getLogger("ranking.sources.semrush")
_BASE = "https://api.semrush.com"


def enabled(keys: SourceKeys) -> bool:
    return bool(keys.semrush)


def _get_csv(keys: SourceKeys, params: Dict[str, str]) -> Optional[list]:
    params = {**params, "key": keys.semrush}
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(_BASE + "/", params=params)
        if resp.status_code != 200 or resp.text.startswith("ERROR"):
            return None
        lines = [ln for ln in resp.text.strip().splitlines() if ln]
        if len(lines) < 2:
            return None
        header = lines[0].split(";")
        rows = [dict(zip(header, ln.split(";"))) for ln in lines[1:]]
        return rows
    except Exception as e:  # pragma: no cover - network
        log.warning("semrush error: %s", e)
        return None


def domain_overview(keys: SourceKeys, website: Optional[str], database: str = "ca") -> Optional[Dict[str, Any]]:
    """Organic keywords / traffic / cost + backlinks summary for a domain."""
    if not enabled(keys):
        return None
    domain = domain_of(website)
    if not domain:
        return None

    out: Dict[str, Any] = {"domain": domain, "available": False}

    rank = _get_csv(keys, {
        "type": "domain_rank",
        "domain": domain,
        "database": database,
        "export_columns": "Dn,Rk,Or,Ot,Oc,Ad",
    })
    if rank:
        r = rank[0]
        out.update(
            available=True,
            organic_keywords=_num(r.get("Or")),
            organic_traffic=_num(r.get("Ot")),
            organic_cost=_num(r.get("Oc")),
        )

    backlinks = _get_csv(keys, {
        "type": "backlinks_overview",
        "target": domain,
        "target_type": "root_domain",
        "export_columns": "ascore,total,domains_num",
    })
    if backlinks:
        b = backlinks[0]
        out.update(
            available=True,
            authority_score=_num(b.get("ascore")),
            backlinks=_num(b.get("total")),
            ref_domains=_num(b.get("domains_num")),
        )
    return out


def _num(s: Any) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None
