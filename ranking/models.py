"""Typed records passed between pipeline stages.

These are plain pydantic models with no DB or network dependencies, so they are
safe to import from tests.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .score import PILLARS  # single source of truth for the pillar list

__all__ = ["PILLARS"]


class Region(BaseModel):
    slug: str
    name: str
    parent_slug: Optional[str] = None
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
    search_radius_m: int = 4000
    is_neighbourhood: bool = True


class Topic(BaseModel):
    slug: str
    title: str
    description: Optional[str] = None
    category: str
    region_slug: str
    hot_score: Optional[float] = None
    included: bool = True
    search_query: Optional[str] = None


class Candidate(BaseModel):
    """A business found during discovery, before dedup/merge into the master table."""

    place_id: Optional[str] = None
    yelp_id: Optional[str] = None
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    category: Optional[str] = None
    discovered_via: str = "google_places"
    discovery_query: Optional[str] = None
    distance_m: Optional[float] = None


class Business(BaseModel):
    id: int
    place_id: Optional[str] = None
    yelp_id: Optional[str] = None
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    canonical_category: Optional[str] = None


class Metric(BaseModel):
    business_id: int
    topic_slug: str
    metric_key: str
    value: Optional[float] = None
    source: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class PillarScore(BaseModel):
    business_id: int
    topic_slug: str
    pillar: str
    raw_score: float
    normalized_score: Optional[float] = None


class Ranking(BaseModel):
    topic_slug: str
    business_id: int
    final_score: float
    rank_position: int
    pillar_breakdown: Dict[str, float] = Field(default_factory=dict)
