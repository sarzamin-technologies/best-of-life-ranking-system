"""Deterministic tests for pillar scoring, normalization, and final combine."""

from ranking import score


def test_pillar_raw_satisfaction_and_digital_defined():
    m = {"sat.cross_rating": 4.5, "sat.consistency": 1.0,
         "digital.has_website": 1.0, "digital.seo_score": 80.0}
    p = score.pillar_raw(m)
    assert p["satisfaction"] is not None and 70 <= p["satisfaction"] <= 80
    # digital is always defined (>=0) even with sparse data
    assert p["digital"] is not None and p["digital"] > 0
    # pillars with no inputs stay None
    assert p["service"] is None
    assert p["search"] is None


def test_pillar_raw_service_penalized_by_complaints():
    base = {"nlp.service_sentiment": 0.8, "nlp.overall_sentiment": 0.8}
    clean = score.pillar_raw(base)["service"]
    noisy = score.pillar_raw({**base, "nlp.complaint_rate": 0.5})["service"]
    assert clean is not None and noisy is not None
    assert noisy < clean


def test_normalize_within_percentile_and_none_imputed():
    vals = [10.0, 20.0, 30.0, None]
    out = score.normalize_within(vals)
    assert out[0] < out[1] < out[2]      # monotonic
    assert out[2] == round((2 + 0.5) / 3 * 100, 2)  # top of 3 known
    assert out[3] == 50.0                # None -> neutral
    # all-None column -> all neutral
    assert score.normalize_within([None, None]) == [50.0, 50.0]


def test_weighted_final_renormalizes_over_present_pillars():
    weights = {"satisfaction": 0.3, "service": 0.2, "popularity": 0.15,
               "digital": 0.15, "search": 0.1, "ai": 0.1}
    # Only two pillars present -> weight renormalizes over (0.3 + 0.2).
    norm = {"satisfaction": 90.0, "service": 40.0}
    expected = (90 * 0.3 + 40 * 0.2) / (0.3 + 0.2)
    assert score.weighted_final(norm, weights) == round(expected, 2)
    # All pillars equal -> final equals that value regardless of weights.
    full = {p: 70.0 for p in weights}
    assert score.weighted_final(full, weights) == 70.0


def test_weighted_final_empty():
    assert score.weighted_final({}, {"satisfaction": 0.3}) == 0.0


def test_end_to_end_ordering_three_businesses():
    """A high-satisfaction popular spot should outrank a hyped 1-review newcomer."""
    weights = {"satisfaction": 0.4, "service": 0.0, "popularity": 0.3,
               "digital": 0.15, "search": 0.0, "ai": 0.15}
    biz = {
        "established": {"sat.cross_rating": 4.6, "pop.review_volume": 800,
                        "digital.has_website": 1.0, "digital.seo_score": 75, "ai.mentioned": 1.0},
        "newcomer":    {"sat.cross_rating": 4.05, "pop.review_volume": 1,
                        "digital.has_website": 0.0, "digital.seo_score": 0, "ai.mentioned": 0.0},
        "midpack":     {"sat.cross_rating": 4.3, "pop.review_volume": 120,
                        "digital.has_website": 1.0, "digital.seo_score": 40, "ai.mentioned": 0.0},
    }
    raw = {k: score.pillar_raw(v) for k, v in biz.items()}
    names = list(biz)
    norm = {k: {} for k in names}
    for pillar in score.PILLARS:
        col = [raw[k][pillar] for k in names]
        for k, nv in zip(names, score.normalize_within(col)):
            if raw[k][pillar] is not None:
                norm[k][pillar] = nv
    finals = {k: score.weighted_final(norm[k], weights) for k in names}
    assert finals["established"] > finals["midpack"] > finals["newcomer"]
