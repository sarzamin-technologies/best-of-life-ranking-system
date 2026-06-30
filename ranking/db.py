"""Postgres access for the DWH: connection, run management, idempotent upserts.

psycopg is imported lazily so the pure-math modules (transform/score helpers,
tests) never require a DB driver or a live connection.
"""

from __future__ import annotations

import datetime as _dt
import json
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from .config import database_url


@contextmanager
def connect() -> Iterator[Any]:
    """Yield a psycopg connection with autocommit off (caller commits)."""
    import psycopg  # lazy

    conn = psycopg.connect(database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def default_run_id(now: Optional[_dt.datetime] = None) -> str:
    now = now or _dt.datetime.now()
    return now.strftime("%Y-%m")


def ensure_run(conn: Any, run_id: str, notes: str = "") -> str:
    """Create the run row if absent. Returns run_id. Idempotent."""
    conn.execute(
        """
        insert into runs (id, notes) values (%s, %s)
        on conflict (id) do nothing
        """,
        (run_id, notes),
    )
    return run_id


def finish_run(conn: Any, run_id: str) -> None:
    conn.execute("update runs set finished_at = now() where id = %s", (run_id,))


# --------------------------------------------------------------------------
# Idempotent upserts. Each returns the affected key(s) where useful.
# --------------------------------------------------------------------------

def upsert_region(conn: Any, r: Dict[str, Any]) -> None:
    conn.execute(
        """
        insert into regions (slug, name, parent_slug, center_lat, center_lng,
                             search_radius_m, is_neighbourhood)
        values (%(slug)s, %(name)s, %(parent_slug)s, %(center_lat)s, %(center_lng)s,
                %(search_radius_m)s, %(is_neighbourhood)s)
        on conflict (slug) do update set
            name = excluded.name,
            parent_slug = excluded.parent_slug,
            center_lat = excluded.center_lat,
            center_lng = excluded.center_lng,
            search_radius_m = excluded.search_radius_m,
            is_neighbourhood = excluded.is_neighbourhood
        """,
        {
            "search_radius_m": 4000,
            "is_neighbourhood": True,
            "parent_slug": None,
            "center_lat": None,
            "center_lng": None,
            **r,
        },
    )


def upsert_topic(conn: Any, t: Dict[str, Any]) -> None:
    conn.execute(
        """
        insert into topics (slug, title, description, category, region_slug,
                            hot_score, included, search_query)
        values (%(slug)s, %(title)s, %(description)s, %(category)s, %(region_slug)s,
                %(hot_score)s, %(included)s, %(search_query)s)
        on conflict (slug) do update set
            title = excluded.title,
            description = excluded.description,
            category = excluded.category,
            region_slug = excluded.region_slug,
            hot_score = coalesce(excluded.hot_score, topics.hot_score),
            included = excluded.included,
            search_query = excluded.search_query
        """,
        {
            "description": None,
            "hot_score": None,
            "included": True,
            "search_query": None,
            **t,
        },
    )


def upsert_business(conn: Any, c: Dict[str, Any], run_id: str) -> int:
    """Insert/merge a business, keyed on place_id. Returns businesses.id.

    Falls back to (yelp_id) or (domain+name) when place_id is absent.
    """
    if c.get("place_id"):
        row = conn.execute(
            """
            insert into businesses (place_id, yelp_id, name, address, lat, lng, phone,
                                    website, domain, canonical_category,
                                    first_seen_run, last_seen_run)
            values (%(place_id)s, %(yelp_id)s, %(name)s, %(address)s, %(lat)s, %(lng)s,
                    %(phone)s, %(website)s, %(domain)s, %(category)s, %(run)s, %(run)s)
            on conflict (place_id) do update set
                yelp_id = coalesce(excluded.yelp_id, businesses.yelp_id),
                name = excluded.name,
                address = coalesce(excluded.address, businesses.address),
                lat = coalesce(excluded.lat, businesses.lat),
                lng = coalesce(excluded.lng, businesses.lng),
                phone = coalesce(excluded.phone, businesses.phone),
                website = coalesce(excluded.website, businesses.website),
                domain = coalesce(excluded.domain, businesses.domain),
                canonical_category = coalesce(excluded.canonical_category, businesses.canonical_category),
                last_seen_run = excluded.last_seen_run
            returning id
            """,
            {"run": run_id, "category": None, "yelp_id": None, "address": None,
             "lat": None, "lng": None, "phone": None, "website": None, "domain": None, **c},
        ).fetchone()
        return int(row[0])

    # No place_id: try to match an existing row by yelp_id or domain+name.
    existing = None
    if c.get("yelp_id"):
        existing = conn.execute(
            "select id from businesses where yelp_id = %s limit 1", (c["yelp_id"],)
        ).fetchone()
    if not existing and c.get("domain"):
        existing = conn.execute(
            "select id from businesses where domain = %s and lower(name) = lower(%s) limit 1",
            (c["domain"], c["name"]),
        ).fetchone()
    if existing:
        bid = int(existing[0])
        conn.execute(
            "update businesses set last_seen_run = %s, "
            "yelp_id = coalesce(yelp_id, %s), website = coalesce(website, %s), "
            "domain = coalesce(domain, %s) where id = %s",
            (run_id, c.get("yelp_id"), c.get("website"), c.get("domain"), bid),
        )
        return bid

    row = conn.execute(
        """
        insert into businesses (yelp_id, name, address, lat, lng, phone, website,
                                domain, canonical_category, first_seen_run, last_seen_run)
        values (%(yelp_id)s, %(name)s, %(address)s, %(lat)s, %(lng)s, %(phone)s,
                %(website)s, %(domain)s, %(category)s, %(run)s, %(run)s)
        returning id
        """,
        {"run": run_id, "category": None, "yelp_id": None, "address": None, "lat": None,
         "lng": None, "phone": None, "website": None, "domain": None, **c},
    ).fetchone()
    return int(row[0])


def reset_topic(conn: Any, topic_slug: str, run_id: str) -> None:
    """Clear a topic's derived rows for a run so re-discovery starts clean.
    Businesses + their raw_collections are kept (shared, idempotent); only the
    topic-scoped links and scores are removed."""
    for table in ("rankings", "pillar_scores", "metrics", "business_topics"):
        conn.execute(
            "delete from %s where topic_slug = %%s and run_id = %%s" % table,
            (topic_slug, run_id),
        )


def link_business_topic(conn: Any, business_id: int, topic_slug: str, run_id: str,
                        via: str, query: Optional[str], distance_m: Optional[float]) -> None:
    conn.execute(
        """
        insert into business_topics (business_id, topic_slug, run_id, discovered_via,
                                     discovery_query, distance_m)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (business_id, topic_slug, run_id) do update set
            discovered_via = excluded.discovered_via,
            discovery_query = coalesce(excluded.discovery_query, business_topics.discovery_query),
            distance_m = coalesce(excluded.distance_m, business_topics.distance_m)
        """,
        (business_id, topic_slug, run_id, via, query, distance_m),
    )


def set_yelp_id(conn: Any, business_id: int, yelp_id: str) -> None:
    conn.execute(
        "update businesses set yelp_id = %s where id = %s and yelp_id is null",
        (yelp_id, business_id),
    )


def save_raw(conn: Any, business_id: int, source: str, run_id: str, payload: Dict[str, Any]) -> None:
    conn.execute(
        """
        insert into raw_collections (business_id, source, run_id, payload)
        values (%s, %s, %s, %s)
        on conflict (business_id, source, run_id) do update set
            payload = excluded.payload, collected_at = now()
        """,
        (business_id, source, run_id, json.dumps(payload)),
    )


def save_metrics(conn: Any, rows: Iterable[Dict[str, Any]], run_id: str) -> None:
    for m in rows:
        conn.execute(
            """
            insert into metrics (business_id, topic_slug, run_id, metric_key, value, source, meta)
            values (%(business_id)s, %(topic_slug)s, %(run)s, %(metric_key)s, %(value)s, %(source)s, %(meta)s)
            on conflict (business_id, topic_slug, run_id, metric_key) do update set
                value = excluded.value, source = excluded.source, meta = excluded.meta
            """,
            {
                "run": run_id,
                "source": None,
                "value": None,
                "meta": json.dumps(m.get("meta", {})),
                **{k: v for k, v in m.items() if k != "meta"},
            },
        )


def save_pillar_scores(conn: Any, rows: Iterable[Dict[str, Any]], run_id: str) -> None:
    for p in rows:
        conn.execute(
            """
            insert into pillar_scores (business_id, topic_slug, run_id, pillar, raw_score, normalized_score)
            values (%(business_id)s, %(topic_slug)s, %(run)s, %(pillar)s, %(raw_score)s, %(normalized_score)s)
            on conflict (business_id, topic_slug, run_id, pillar) do update set
                raw_score = excluded.raw_score, normalized_score = excluded.normalized_score
            """,
            {"run": run_id, "normalized_score": None, **p},
        )


def save_ranking(conn: Any, r: Dict[str, Any], run_id: str) -> None:
    conn.execute(
        """
        insert into rankings (topic_slug, business_id, run_id, final_score, rank_position, pillar_breakdown)
        values (%(topic_slug)s, %(business_id)s, %(run)s, %(final_score)s, %(rank_position)s, %(pillar_breakdown)s)
        on conflict (topic_slug, business_id, run_id) do update set
            final_score = excluded.final_score,
            rank_position = excluded.rank_position,
            pillar_breakdown = excluded.pillar_breakdown
        """,
        {"run": run_id, "pillar_breakdown": json.dumps(r.get("pillar_breakdown", {})),
         **{k: v for k, v in r.items() if k != "pillar_breakdown"}},
    )


# --------------------------------------------------------------------------
# Reads used by later stages.
# --------------------------------------------------------------------------

def included_topics(conn: Any, only: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    sql = (
        "select t.slug, t.title, t.category, t.region_slug, t.search_query, "
        "r.name as region_name, r.center_lat, r.center_lng, r.search_radius_m "
        "from topics t join regions r on r.slug = t.region_slug "
        "where t.included = true"
    )
    params: List[Any] = []
    if only:
        sql += " and t.slug = any(%s)"
        params.append(list(only))
    sql += " order by t.slug"
    cur = conn.execute(sql, params)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def topic_business_count(conn: Any, topic_slug: str, run_id: str) -> int:
    return int(conn.execute(
        "select count(*) from business_topics where topic_slug = %s and run_id = %s",
        (topic_slug, run_id),
    ).fetchone()[0])


def collected_business_ids(conn: Any, run_id: str) -> set:
    """Business ids that already have at least one raw collection this run — used to
    resume `collect` without re-fetching (and re-paying for) finished businesses."""
    cur = conn.execute(
        "select distinct business_id from raw_collections where run_id = %s", (run_id,)
    )
    return {r[0] for r in cur.fetchall()}


def businesses_for_topic(conn: Any, topic_slug: str, run_id: str) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        select b.id, b.place_id, b.yelp_id, b.name, b.address, b.lat, b.lng,
               b.website, b.domain
        from businesses b
        join business_topics bt on bt.business_id = b.id
        where bt.topic_slug = %s and bt.run_id = %s
        """,
        (topic_slug, run_id),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def raw_for_topic(conn: Any, topic_slug: str, run_id: str) -> List[Dict[str, Any]]:
    """All raw collections for businesses in a topic, this run."""
    cur = conn.execute(
        """
        select rc.business_id, rc.source, rc.payload
        from raw_collections rc
        join business_topics bt on bt.business_id = rc.business_id
        where bt.topic_slug = %s and bt.run_id = %s and rc.run_id = %s
        """,
        (topic_slug, run_id, run_id),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def metrics_for_topic(conn: Any, topic_slug: str, run_id: str) -> List[Dict[str, Any]]:
    cur = conn.execute(
        "select business_id, metric_key, value from metrics "
        "where topic_slug = %s and run_id = %s",
        (topic_slug, run_id),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def set_photo(conn: Any, business_id: int, photo_url: str) -> None:
    conn.execute("update businesses set photo_url = %s where id = %s", (photo_url, business_id))


def set_strengths(conn: Any, topic_slug: str, business_id: int, run_id: str,
                  bullets: List[str]) -> None:
    conn.execute(
        "update rankings set strengths = %s where topic_slug = %s and business_id = %s and run_id = %s",
        (json.dumps(bullets), topic_slug, business_id, run_id),
    )


def ranking_for_topic(conn: Any, topic_slug: str, run_id: str) -> List[Dict[str, Any]]:
    """Full ranking rows for export/import: rank + score + every business field the
    website's `nominees` table wants, plus Google rating/review_count from metrics."""
    cur = conn.execute(
        """
        select rk.topic_slug, rk.business_id, rk.rank_position, rk.final_score,
               rk.pillar_breakdown, rk.strengths,
               b.name, b.place_id, b.website, b.address, b.lat, b.lng, b.phone, b.photo_url,
               gr.value  as rating,
               grc.value as rating_count
        from rankings rk
        join businesses b on b.id = rk.business_id
        left join metrics gr  on gr.business_id = b.id and gr.topic_slug = rk.topic_slug
                              and gr.run_id = rk.run_id and gr.metric_key = 'google.rating'
        left join metrics grc on grc.business_id = b.id and grc.topic_slug = rk.topic_slug
                              and grc.run_id = rk.run_id and grc.metric_key = 'google.review_count'
        where rk.topic_slug = %s and rk.run_id = %s
        order by rk.rank_position
        """,
        (topic_slug, run_id),
    )
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
