"""Stage 4 — raw payloads -> normalized numeric metrics.

The functions at the top are pure (no DB, no network, lazy NLP import) so they
are unit-tested directly. `run_transform` is the orchestrator that reads
raw_collections for a topic and writes the `metrics` table.
"""

from __future__ import annotations

import math
import re
import time
from typing import Any, Dict, List, Optional, Sequence

# Aspect keywords for service-quality tagging of review text.
ASPECTS: Dict[str, List[str]] = {
    "service": ["service", "staff", "server", "waiter", "waitress", "friendly", "rude", "attentive", "helpful"],
    "wait": ["wait", "waited", "slow", "quick", "fast", "line", "lineup", "reservation"],
    "cleanliness": ["clean", "dirty", "hygiene", "spotless", "filthy", "tidy"],
    "value": ["price", "expensive", "cheap", "value", "worth", "overpriced", "affordable"],
}
COMPLAINT_WORDS = ["never", "worst", "rude", "dirty", "cold", "wrong", "refund", "disappointed", "awful", "terrible"]


# --------------------------------------------------------------------------
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------

def bayesian_rating(rating: Optional[float], count: Optional[int],
                    prior_mean: float = 4.0, prior_strength: float = 20.0) -> Optional[float]:
    """Shrink a rating toward the prior mean by review volume.

    A 5.0 from 1 review lands near the prior; an 800-review 4.6 stays near 4.6.
    """
    if rating is None or count is None or count <= 0:
        return None
    return (prior_strength * prior_mean + count * rating) / (prior_strength + count)


def vader_scores(texts: Sequence[str]) -> Dict[str, float]:
    """Aggregate VADER sentiment over review texts. Lazy import so tests that
    don't exercise sentiment never need the dependency."""
    texts = [t for t in texts if t]
    if not texts:
        return {"positive": 0.0, "neutral": 0.0, "negative": 0.0, "compound": 0.0}
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # lazy

    an = SentimentIntensityAnalyzer()
    pos = neu = neg = comp = 0
    for t in texts:
        s = an.polarity_scores(t)
        comp += s["compound"]
        if s["compound"] >= 0.05:
            pos += 1
        elif s["compound"] <= -0.05:
            neg += 1
        else:
            neu += 1
    n = len(texts)
    return {"positive": pos / n, "neutral": neu / n, "negative": neg / n, "compound": comp / n}


def aspect_sentiment(texts: Sequence[str], aspect: str) -> Optional[float]:
    """Mean VADER compound over reviews that mention an aspect's keywords.
    Returns None if no review mentions the aspect."""
    kws = ASPECTS.get(aspect, [])
    hit = [t for t in texts if t and any(k in t.lower() for k in kws)]
    if not hit:
        return None
    return vader_scores(hit)["compound"]


def complaint_rate(texts: Sequence[str]) -> float:
    texts = [t for t in texts if t]
    if not texts:
        return 0.0
    flagged = sum(1 for t in texts if any(w in t.lower() for w in COMPLAINT_WORDS))
    return flagged / len(texts)


def seo_quality_score(audit: Optional[Dict[str, Any]]) -> float:
    """0..100 website quality from a firecrawl audit dict (no website -> 0)."""
    if not audit or not audit.get("fetched"):
        return 0.0
    score = 0.0
    score += 25 if audit.get("is_https") else 0
    score += 15 if audit.get("has_viewport") else 0
    score += 15 if audit.get("has_schema_org") else 0
    score += 10 if audit.get("has_open_graph") else 0
    score += 10 if audit.get("has_canonical") else 0
    score += 10 if (audit.get("h1_count") or 0) >= 1 else 0
    wc = audit.get("word_count") or 0
    score += min(15, wc / 80.0)  # content depth, capped
    return round(min(100.0, score), 2)


def recency_days(publish_times: Sequence[str], now: Optional[float] = None) -> Optional[float]:
    """Median age in days of review timestamps (ISO8601 or epoch seconds)."""
    now = now if now is not None else time.time()
    ages = []
    for ts in publish_times:
        epoch = _to_epoch(ts)
        if epoch:
            ages.append((now - epoch) / 86400.0)
    if not ages:
        return None
    ages.sort()
    return ages[len(ages) // 2]


def _to_epoch(ts: Any) -> Optional[float]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        import datetime as dt
        try:
            return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).timestamp()
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Raw payload extraction
# --------------------------------------------------------------------------

def _google_review_texts(payload: Dict[str, Any]) -> List[str]:
    out = []
    for r in payload.get("reviews", []) or []:
        t = (r.get("text") or {})
        txt = t.get("text") if isinstance(t, dict) else t
        if txt:
            out.append(txt)
    return out


def _google_review_times(payload: Dict[str, Any]) -> List[str]:
    return [r.get("publishTime") for r in payload.get("reviews", []) or [] if r.get("publishTime")]


def _yelp_review_texts(payload: Dict[str, Any]) -> List[str]:
    return [r.get("text") for r in payload.get("reviews", []) or [] if r.get("text")]


def metrics_for_business(topic_slug: str, business_id: int,
                         raws: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build the metric rows for one business from its per-source raw payloads.

    `raws` maps source -> payload. Missing sources are simply skipped.
    """
    out: List[Dict[str, Any]] = []

    def add(key: str, value: Optional[float], source: str, **meta: Any) -> None:
        if value is None:
            return
        out.append({"business_id": business_id, "topic_slug": topic_slug,
                    "metric_key": key, "value": float(value), "source": source, "meta": meta})

    # --- Google ---
    g = raws.get("google_places") or {}
    g_rating = g.get("rating")
    g_count = g.get("userRatingCount")
    add("google.rating", g_rating, "google_places")
    add("google.review_count", g_count, "google_places")
    add("google.rating_bayes", bayesian_rating(g_rating, g_count), "google_places")
    g_texts = _google_review_texts(g)

    # --- Yelp ---
    y = raws.get("yelp") or {}
    y_rating = y.get("rating")
    y_count = y.get("review_count")
    add("yelp.rating", y_rating, "yelp")
    add("yelp.review_count", y_count, "yelp")
    add("yelp.rating_bayes", bayesian_rating(y_rating, y_count), "yelp")
    y_texts = _yelp_review_texts(y)

    # --- Combined satisfaction (weighted by review volume across platforms) ---
    parts = [(bayesian_rating(g_rating, g_count), g_count or 0),
             (bayesian_rating(y_rating, y_count), y_count or 0)]
    parts = [(r, w) for r, w in parts if r is not None]
    if parts:
        wsum = sum(w for _, w in parts) or len(parts)
        if sum(w for _, w in parts) == 0:
            cross = sum(r for r, _ in parts) / len(parts)
        else:
            cross = sum(r * w for r, w in parts) / wsum
        add("sat.cross_rating", cross, "combined")
        if len(parts) > 1:
            spread = max(r for r, _ in parts) - min(r for r, _ in parts)
            add("sat.consistency", max(0.0, 1.0 - spread / 2.0), "combined")

    # --- Service-quality NLP over all review text ---
    texts = g_texts + y_texts
    if texts:
        sv = aspect_sentiment(texts, "service")
        add("nlp.service_sentiment", sv, "nlp")
        add("nlp.wait_sentiment", aspect_sentiment(texts, "wait"), "nlp")
        add("nlp.cleanliness_sentiment", aspect_sentiment(texts, "cleanliness"), "nlp")
        add("nlp.value_sentiment", aspect_sentiment(texts, "value"), "nlp")
        add("nlp.complaint_rate", complaint_rate(texts), "nlp")
        add("nlp.overall_sentiment", vader_scores(texts)["compound"], "nlp")
        add("nlp.review_recency_days", recency_days(_google_review_times(g)), "nlp")

    # --- Popularity ---
    total_reviews = (g_count or 0) + (y_count or 0)
    add("pop.review_volume", total_reviews, "combined")
    add("pop.cross_platform", float(len(parts)), "combined")  # 1 or 2 platforms
    r_red = raws.get("reddit") or {}
    add("pop.reddit_mentions", r_red.get("count"), "reddit")
    w = raws.get("web_search") or {}
    if w:
        add("pop.web_mentions", 1.0 if w.get("mentioned") else 0.0, "web_search")

    # --- Digital presence ---
    site = (raws.get("site") or {}).get("website")
    add("digital.has_website", 1.0 if (g.get("websiteUri") or site) else 0.0, "combined")
    add("digital.seo_score", seo_quality_score(raws.get("firecrawl")), "firecrawl")

    # --- Search visibility ---
    sem = raws.get("semrush") or {}
    if sem.get("available"):
        add("search.authority", sem.get("authority_score"), "semrush")
        add("search.organic_traffic", sem.get("organic_traffic"), "semrush")
        add("search.organic_keywords", sem.get("organic_keywords"), "semrush")
    if w and w.get("serp_rank"):
        # invert: rank 1 -> 100, rank 20 -> ~5
        add("search.serp_score", max(0.0, 100.0 - (w["serp_rank"] - 1) * 5.0), "web_search")

    # --- AI visibility ---
    ai = raws.get("ai_search") or {}
    if ai:
        add("ai.mentioned", 1.0 if ai.get("mentioned") else 0.0, "ai_search")

    return out


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

def run_transform(topics: Sequence[str], run_id: str) -> None:
    from . import db  # lazy

    with db.connect() as conn:
        for topic in topics:
            rows = db.raw_for_topic(conn, topic, run_id)
            by_biz: Dict[int, Dict[str, Any]] = {}
            for r in rows:
                by_biz.setdefault(r["business_id"], {})[r["source"]] = r["payload"]
            metric_rows: List[Dict[str, Any]] = []
            for bid, raws in by_biz.items():
                metric_rows.extend(metrics_for_business(topic, bid, raws))
            db.save_metrics(conn, metric_rows, run_id)
            print("  transform %-45s %3d businesses, %4d metrics"
                  % (topic, len(by_biz), len(metric_rows)))
