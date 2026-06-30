"""Deterministic tests for the transform math. No DB, no network, no NLP deps."""

from ranking import transform as tx


def test_bayesian_shrinks_low_volume_toward_prior():
    # 1 review at 5.0 should land well below an 800-review 4.6.
    hyped = tx.bayesian_rating(5.0, 1, prior_mean=4.0, prior_strength=20)
    solid = tx.bayesian_rating(4.6, 800, prior_mean=4.0, prior_strength=20)
    assert hyped is not None and solid is not None
    assert hyped < solid
    assert abs(hyped - 4.05) < 0.05      # ~ (20*4 + 1*5)/21
    assert abs(solid - 4.585) < 0.02     # barely moved


def test_bayesian_none_on_missing():
    assert tx.bayesian_rating(None, 10) is None
    assert tx.bayesian_rating(4.5, 0) is None
    assert tx.bayesian_rating(4.5, None) is None


def test_complaint_rate():
    texts = ["worst service ever", "lovely spot", "food was cold and wrong"]
    assert tx.complaint_rate(texts) == 2 / 3
    assert tx.complaint_rate([]) == 0.0


def test_seo_quality_score_bounds_and_signals():
    assert tx.seo_quality_score(None) == 0.0
    assert tx.seo_quality_score({"fetched": False}) == 0.0
    full = {
        "fetched": True, "is_https": True, "has_viewport": True, "has_schema_org": True,
        "has_open_graph": True, "has_canonical": True, "h1_count": 1, "word_count": 2000,
    }
    s = tx.seo_quality_score(full)
    assert 95 <= s <= 100
    # An https-only site scores far lower.
    assert tx.seo_quality_score({"fetched": True, "is_https": True}) < s


def test_metrics_for_business_combines_platforms():
    raws = {
        "google_places": {"rating": 4.6, "userRatingCount": 800, "websiteUri": "https://x.com",
                          "reviews": []},
        "yelp": {"rating": 4.0, "review_count": 100, "reviews": []},
        "site": {"website": "https://x.com"},
        "reddit": {"count": 3},
        "ai_search": {"mentioned": True},
    }
    rows = tx.metrics_for_business("best-coffee-downtown-toronto", 1, raws)
    keys = {r["metric_key"]: r["value"] for r in rows}
    assert keys["google.rating_bayes"] > keys["yelp.rating_bayes"]
    assert "sat.cross_rating" in keys
    # volume-weighted cross rating sits between the two platform bayes ratings
    assert keys["yelp.rating_bayes"] <= keys["sat.cross_rating"] <= keys["google.rating_bayes"]
    assert keys["pop.review_volume"] == 900
    assert keys["digital.has_website"] == 1.0
    assert keys["ai.mentioned"] == 1.0


def test_recency_days_median():
    # Two timestamps; one ~10 days old, one ~30. now fixed for determinism.
    import datetime as dt
    now = dt.datetime(2026, 1, 31).timestamp()
    d = tx.recency_days(["2026-01-21", "2026-01-01"], now=now)
    assert d is not None and 9 <= d <= 31
