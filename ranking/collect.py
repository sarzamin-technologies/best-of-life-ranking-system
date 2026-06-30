"""Stage 3 — gather every public datapoint about each discovered business.

Per topic we fetch two topic-level signals once (the LLM's recommendation list and
the web SERP for "best X in <hood>"), then per business we pull Google details +
reviews, Yelp details + reviews, Firecrawl website audit, SEMrush domain metrics, and
Reddit mentions. Everything lands in `raw_collections` (jsonb), one row per
(business, source, run) — idempotent, so partial re-runs are cheap. Sources with no
key are simply skipped.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from . import db
from .config import SourceKeys, overrides as load_overrides
from .sources import google_places, yelp, firecrawl, semrush, reddit, web_search, ai_search
from .sources._http import domain_of

log = logging.getLogger("ranking.collect")


def _norm_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(the|inc|ltd|llc|co|corp|restaurant|cafe|bar|shop|store)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _match(name: str, text: Optional[str]) -> bool:
    n = _norm_name(name)
    return len(n) >= 3 and bool(text) and n in _norm_name(text)


def _safe(label: str, fn, *a, **kw):
    """Run a source fetch; on any error log and return None so one flaky API call
    never aborts the run."""
    try:
        return fn(*a, **kw)
    except Exception as e:  # pragma: no cover - network
        log.warning("collect %s failed: %s", label, str(e)[:140])
        return None


def _apply_overrides(conn: Any, keys: SourceKeys, run_id: str) -> None:
    """Apply manual factual corrections (config/overrides.yaml) regardless of the
    resume-skip, so they take effect every run even on already-collected businesses.
    Currently corrects the website (and re-scrapes it for an accurate digital signal).
    Corrects data only — never rankings."""
    ovs = load_overrides()
    if not ovs:
        return
    applied = 0
    for place_id, fields in ovs.items():
        site = fields.get("website")
        row = conn.execute(
            "select id, website from businesses where place_id = %s", (place_id,)
        ).fetchone()
        if not row:
            continue
        bid, current = row
        if site and site != current:
            conn.execute("update businesses set website = %s where id = %s", (site, bid))
            db.save_raw(conn, bid, "site", run_id, {"website": site})
            if firecrawl.enabled(keys):
                fc = _safe("override-firecrawl", firecrawl.scrape, keys, site)
                if fc:
                    db.save_raw(conn, bid, "firecrawl", run_id, fc)
            conn.commit()
            applied += 1
    if applied:
        print("  overrides applied to %d business(es)" % applied)


def run_collect(topics: Sequence[Dict[str, Any]], run_id: str) -> None:
    keys = SourceKeys()
    with db.connect() as conn:
        db.ensure_run(conn, run_id, "collect")
        conn.commit()
        _apply_overrides(conn, keys, run_id)
        # Resume support: skip businesses already collected this run (idempotent,
        # avoids re-spending API calls). A fresh month = new run_id = full collect.
        already = db.collected_business_ids(conn, run_id)
        for t in topics:
            biz = db.businesses_for_topic(conn, t["slug"], run_id)
            todo = [b for b in biz if b["id"] not in already]
            if not todo:
                print("  collect %-45s skipped (already done)" % t["slug"])
                continue

            # Topic-level signals, fetched once (resilient).
            ai_names = (_safe("ai_recs", ai_search.ask_recommendations, keys, t["title"],
                              t.get("region_name", "Toronto")) or []) if ai_search.enabled(keys) else []
            serp_query = "best %s %s" % (_term(t["title"]), t.get("region_name", "Toronto"))
            serp = (_safe("web_search", web_search.search, keys, serp_query) or []) \
                if web_search.enabled(keys) else []

            done = 0
            for b in todo:
                try:
                    _collect_one(conn, keys, b, run_id, ai_names, serp)
                    conn.commit()  # per-business: durable + resumable on crash
                    already.add(b["id"])
                    done += 1
                except Exception as e:
                    conn.rollback()
                    log.warning("collect business %s (%s) failed: %s", b.get("id"), b.get("name"), str(e)[:140])
            print("  collect %-45s %3d/%d new (%d already done)"
                  % (t["slug"], done, len(todo), len(biz) - len(todo)))


def _collect_one(conn: Any, keys: SourceKeys, b: Dict[str, Any], run_id: str,
                 ai_names: List[str], serp: List[Dict[str, Any]]) -> None:
    bid = b["id"]
    website = b.get("website")

    # Google details + reviews
    if b.get("place_id") and google_places.enabled(keys):
        g = _safe("google", google_places.place_details, keys, b["place_id"])
        if g:
            db.save_raw(conn, bid, "google_places", run_id, g)
            website = website or g.get("websiteUri")

    # Yelp business + reviews. Use the known yelp_id if discovery merged one;
    # otherwise look the business up on Yelp by name+location for cross-platform
    # coverage, and persist the discovered id for future runs.
    if yelp.enabled(keys):
        if b.get("yelp_id"):
            yb = _safe("yelp.business", yelp.business, keys, b["yelp_id"])
        else:
            yb = _safe("yelp.match", yelp.match_business, keys, b["name"], b.get("lat"),
                       b.get("lng"), b.get("address"))
            if yb and yb.get("id"):
                db.set_yelp_id(conn, bid, yb["id"])
        if yb:
            yid = b.get("yelp_id") or yb.get("id")
            yr = _safe("yelp.reviews", yelp.reviews, keys, yid) if yid else {}
            yb["reviews"] = (yr or {}).get("reviews", [])
            db.save_raw(conn, bid, "yelp", run_id, yb)

    # Record the resolved website so transform can flag digital presence.
    if website:
        db.save_raw(conn, bid, "site", run_id, {"website": website})

    # Firecrawl website audit
    if website and firecrawl.enabled(keys):
        fc = _safe("firecrawl", firecrawl.scrape, keys, website)
        if fc:
            db.save_raw(conn, bid, "firecrawl", run_id, fc)

    # SEMrush domain metrics
    if website and semrush.enabled(keys):
        sem = semrush.domain_overview(keys, website)
        if sem:
            db.save_raw(conn, bid, "semrush", run_id, sem)

    # Reddit mentions
    if reddit.enabled(keys):
        rd = reddit.search_mentions(keys, b["name"])
        db.save_raw(conn, bid, "reddit", run_id, rd)

    # Web SERP visibility for this business within the topic SERP. "best X"
    # queries return listicles, so a business usually appears inside a result's
    # snippet rather than as its own ranked page — match title, snippet, and domain.
    if serp:
        rank = None
        dom = domain_of(website)
        for r in serp:
            if _match(b["name"], r.get("title")) or _match(b["name"], r.get("snippet")) \
                    or (dom and dom in (r.get("url") or "")):
                rank = r.get("position")
                break
        db.save_raw(conn, bid, "web_search", run_id,
                    {"query_results": len(serp), "serp_rank": rank, "mentioned": rank is not None})

    # AI recommendation mention
    if ai_names:
        mentioned = any(_match(b["name"], n) or _match(n, b["name"]) for n in ai_names)
        db.save_raw(conn, bid, "ai_search", run_id, {"mentioned": mentioned, "recommended": ai_names})


def _term(title: str) -> str:
    core = title
    for p in ("Best ", "best "):
        if core.startswith(p):
            core = core[len(p):]
    if " in " in core:
        core = core.rsplit(" in ", 1)[0]
    return core.strip()
