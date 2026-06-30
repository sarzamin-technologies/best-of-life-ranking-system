"""Configuration: env vars, paths, and the tunable weights/catalog files.

Importing this module is cheap and has no side effects beyond reading .env.
Nothing here connects to a database or a network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv missing is fine
    pass

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
EXPORTS_DIR = ROOT / "exports"
CACHE_DIR = ROOT / ".cache"


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default) or default


@dataclass(frozen=True)
class SourceKeys:
    """Resolved API keys. Empty string => source disabled (skipped, not an error)."""

    google_maps: str = field(default_factory=lambda: env("GOOGLE_MAPS_API_KEY"))
    yelp: str = field(default_factory=lambda: env("YELP_API_KEY"))
    firecrawl: str = field(default_factory=lambda: env("FIRECRAWL_API_KEY"))
    semrush: str = field(default_factory=lambda: env("SEMRUSH_API_KEY"))
    web_search: str = field(default_factory=lambda: env("WEB_SEARCH_API_KEY"))
    web_search_provider: str = field(default_factory=lambda: env("WEB_SEARCH_PROVIDER", "serpapi"))
    reddit_client_id: str = field(default_factory=lambda: env("REDDIT_CLIENT_ID"))
    reddit_client_secret: str = field(default_factory=lambda: env("REDDIT_CLIENT_SECRET"))
    reddit_user_agent: str = field(default_factory=lambda: env("REDDIT_USER_AGENT", "ontario-ranking/0.1"))
    ai_provider: str = field(default_factory=lambda: env("AI_PROVIDER", "openai"))
    ai_api_key: str = field(default_factory=lambda: env("AI_API_KEY"))
    ai_model: str = field(default_factory=lambda: env("AI_MODEL", "gpt-4o-mini"))
    lovable: str = field(default_factory=lambda: env("LOVABLE_API_KEY"))


def database_url() -> str:
    url = env("DWH_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DWH_DATABASE_URL is not set. Copy .env.example to .env and configure it "
            "(or `docker compose up -d` for the bundled local Postgres)."
        )
    return url


def import_endpoint() -> tuple:
    """(url, secret) for the website's import route, used ONLY by the import step.
    Lovable Cloud hides the DB URL / service-role key, so we POST to the site's
    secured /api/public/import-rankings endpoint instead."""
    url = env("IMPORT_ENDPOINT_URL")
    if not url:
        raise RuntimeError(
            "IMPORT_ENDPOINT_URL is not set. Add it to .env "
            "(e.g. https://best-of.life/api/public/import-rankings)."
        )
    return url, env("IMPORT_SECRET", "import-best-of-ontario-2026")


@lru_cache(maxsize=1)
def weights() -> Dict[str, Any]:
    """Pillar weights + per-pillar signal weights, from config/weights.yaml."""
    path = CONFIG_DIR / "weights.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def catalog() -> Dict[str, Any]:
    """The curated topic×neighbourhood catalog, from config/topics.seed.yaml."""
    path = CONFIG_DIR / "topics.seed.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def overrides() -> Dict[str, Dict[str, Any]]:
    """Manual factual data corrections keyed by Google place_id (config/overrides.yaml).
    Returns {} if the file is absent. Corrects data only — never rankings."""
    path = CONFIG_DIR / "overrides.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("businesses", {}) or {}
