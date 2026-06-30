"""Nominee slug generation — must match the website's seed-nominees.ts exactly so
the importer upserts the same rows the site already created:

    slug = `${slugify(name)}-${place_id.slice(-6)}`
"""

from __future__ import annotations

import re
from typing import Optional


def slugify(s: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:80]
    return out or "nominee"


def nominee_slug(name: str, place_id: Optional[str]) -> str:
    base = slugify(name)
    suffix = (place_id or "")[-6:]
    return "%s-%s" % (base, suffix) if suffix else base
