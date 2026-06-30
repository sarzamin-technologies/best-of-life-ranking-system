"""Stage 5 — metrics -> pillar sub-scores -> weighted final rank.

Pure functions (pillar_raw, normalize_within, weighted_final) are unit-tested.
`run_score` reads the `metrics` table, computes pillars, normalizes WITHIN each
topic, applies config weights, and writes `pillar_scores` + `rankings`.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

# The six pillars, in display order. Defined here (no heavy deps) so the pure
# scoring functions can be imported by tests without pulling in pydantic.
PILLARS: List[str] = ["satisfaction", "service", "popularity", "digital", "search", "ai"]


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _sent_to_100(s: Optional[float]) -> Optional[float]:
    """Map a VADER compound (-1..1) to 0..100."""
    if s is None:
        return None
    return _clamp((s + 1.0) / 2.0 * 100.0)


def pillar_raw(m: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Compute the six raw (absolute, 0..100) pillar scores for one business
    from its metric_key -> value dict. None = no data for that pillar."""
    out: Dict[str, Optional[float]] = {p: None for p in PILLARS}

    # Satisfaction — Bayesian cross-platform rating + consistency.
    cross = m.get("sat.cross_rating")
    if cross is not None:
        base = _clamp((cross - 3.0) / 2.0 * 100.0)
        cons = m.get("sat.consistency")
        out["satisfaction"] = base if cons is None else base * 0.9 + _clamp(cons * 100.0) * 0.1

    # Service — aspect + overall sentiment, penalized by complaint rate.
    parts = [
        _sent_to_100(m.get("nlp.service_sentiment")),
        _sent_to_100(m.get("nlp.overall_sentiment")),
        _sent_to_100(m.get("nlp.wait_sentiment")),
        _sent_to_100(m.get("nlp.cleanliness_sentiment")),
        _sent_to_100(m.get("nlp.value_sentiment")),
    ]
    parts = [p for p in parts if p is not None]
    if parts:
        svc = sum(parts) / len(parts)
        svc -= (m.get("nlp.complaint_rate") or 0.0) * 30.0
        out["service"] = _clamp(svc)

    # Popularity — review volume (log) + reddit buzz + cross-platform presence.
    vol = m.get("pop.review_volume")
    if vol is not None or m.get("pop.reddit_mentions") is not None:
        vol_score = min(100.0, math.log10((vol or 0) + 1) * 40.0)
        reddit = min(100.0, (m.get("pop.reddit_mentions") or 0.0) * 12.0)
        cross_bonus = ((m.get("pop.cross_platform") or 1.0) - 1.0) * 10.0
        web = (m.get("pop.web_mentions") or 0.0) * 10.0
        out["popularity"] = _clamp(0.65 * vol_score + 0.2 * reddit + cross_bonus + web)

    # Digital presence — always defined (0 if no usable site).
    seo = m.get("digital.seo_score") or 0.0
    has = m.get("digital.has_website") or 0.0
    out["digital"] = _clamp(has * 20.0 + seo * 0.8)

    # Search visibility — SEMrush authority/traffic + SERP rank.
    sp = []
    if m.get("search.authority") is not None:
        sp.append(_clamp(m["search.authority"]))
    if m.get("search.organic_traffic") is not None:
        sp.append(min(100.0, math.log10(m["search.organic_traffic"] + 1) * 25.0))
    if m.get("search.serp_score") is not None:
        sp.append(_clamp(m["search.serp_score"]))
    if sp:
        out["search"] = sum(sp) / len(sp)

    # AI visibility — recommended by the model or not.
    if m.get("ai.mentioned") is not None:
        out["ai"] = _clamp(m["ai.mentioned"] * 100.0)

    return out


def normalize_within(values: Sequence[Optional[float]]) -> List[float]:
    """Percentile-rank a column of pillar scores to 0..100 within a topic.

    None (no data) is imputed to 50 (neutral) so missing a single signal neither
    rewards nor punishes a business relative to peers. Ties share the mid-rank.
    """
    known = [v for v in values if v is not None]
    if not known:
        return [50.0 for _ in values]
    n = len(known)
    out: List[float] = []
    for v in values:
        if v is None:
            out.append(50.0)
            continue
        less = sum(1 for k in known if k < v)
        equal = sum(1 for k in known if k == v)
        out.append(round((less + 0.5 * equal) / n * 100.0, 2))
    return out


def weighted_final(normalized: Dict[str, float], weights: Dict[str, float]) -> float:
    """Weighted sum of normalized pillars -> 0..100. Renormalizes weights over
    whichever pillars are present so a missing pillar doesn't shrink the total."""
    num = 0.0
    wsum = 0.0
    for pillar, w in weights.items():
        if pillar in normalized:
            num += normalized[pillar] * w
            wsum += w
    return round(num / wsum, 2) if wsum else 0.0


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

def run_score(topics: Sequence[str], run_id: str) -> None:
    from . import config, db  # lazy

    cfg = config.weights()
    weights = cfg["pillars"]

    with db.connect() as conn:
        for topic in topics:
            rows = db.metrics_for_topic(conn, topic, run_id)
            # business_id -> {metric_key: value}
            by_biz: Dict[int, Dict[str, float]] = {}
            for r in rows:
                if r["value"] is not None:
                    by_biz.setdefault(r["business_id"], {})[r["metric_key"]] = float(r["value"])
            if not by_biz:
                print("  score %-45s no metrics, skipped" % topic)
                continue

            bids = list(by_biz.keys())
            raw_by_biz = {b: pillar_raw(by_biz[b]) for b in bids}

            # Normalize each pillar within the topic.
            norm_by_biz: Dict[int, Dict[str, float]] = {b: {} for b in bids}
            for pillar in PILLARS:
                col = [raw_by_biz[b][pillar] for b in bids]
                normed = normalize_within(col)
                for b, nv in zip(bids, normed):
                    # only keep pillars that had data for this business
                    if raw_by_biz[b][pillar] is not None:
                        norm_by_biz[b][pillar] = nv

            # Persist pillar scores + compute final.
            pillar_rows = []
            finals = []
            for b in bids:
                for pillar in PILLARS:
                    raw = raw_by_biz[b][pillar]
                    if raw is None:
                        continue
                    pillar_rows.append({
                        "business_id": b, "topic_slug": topic, "pillar": pillar,
                        "raw_score": round(raw, 2), "normalized_score": norm_by_biz[b].get(pillar),
                    })
                final = weighted_final(norm_by_biz[b], weights)
                finals.append((b, final, norm_by_biz[b]))
            db.save_pillar_scores(conn, pillar_rows, run_id)

            # Rank: highest final first; tie-break by satisfaction then review volume.
            finals.sort(key=lambda t: (t[1], t[2].get("satisfaction", 0),
                                       by_biz[t[0]].get("pop.review_volume", 0)), reverse=True)
            for pos, (b, final, breakdown) in enumerate(finals, start=1):
                db.save_ranking(conn, {
                    "topic_slug": topic, "business_id": b, "final_score": final,
                    "rank_position": pos,
                    "pillar_breakdown": {k: round(v, 1) for k, v in breakdown.items()},
                }, run_id)
            print("  score %-45s %3d ranked (top final=%.1f)"
                  % (topic, len(finals), finals[0][1] if finals else 0))
