"""AI search / LLM client with a provider adapter: openai | anthropic | lovable.

Three uses across the pipeline:
  - ask_recommendations(): "best X in <hood>" -> list of business names an LLM
    recommends (AI-visibility mention rate, mirrors ai-visibility.server.ts)
  - classify_service(): optional nuanced service-quality tag for review text
  - complete(): generic JSON completion used by the catalog hot-pair nominator
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from ..config import CACHE_DIR, SourceKeys
from ._http import post_json

log = logging.getLogger("ranking.sources.ai")

_RECS_CACHE = os.path.join(CACHE_DIR, "ai_recommendations.json")


def _cache_load() -> Dict[str, List[str]]:
    try:
        with open(_RECS_CACHE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _cache_store(data: Dict[str, List[str]]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_RECS_CACHE, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def enabled(keys: SourceKeys) -> bool:
    return bool(keys.ai_api_key or keys.lovable)


def complete(keys: SourceKeys, prompt: str, system: str = "", max_tokens: int = 800) -> str:
    if not enabled(keys):
        return ""
    provider = (keys.ai_provider or "openai").lower()
    try:
        if provider == "anthropic":
            return _anthropic(keys, prompt, system, max_tokens)
        # openai-compatible (openai or lovable gateway)
        return _openai_compatible(keys, prompt, system, max_tokens)
    except Exception as e:  # pragma: no cover - network
        log.warning("ai complete failed: %s", e)
        return ""


def _openai_compatible(keys: SourceKeys, prompt: str, system: str, max_tokens: int) -> str:
    provider = (keys.ai_provider or "openai").lower()
    if provider == "agnic":
        # Agnic AI gateway — OpenAI-compatible, models named "provider/model".
        url, token = "https://api.agnic.ai/v1/chat/completions", keys.ai_api_key
    elif keys.ai_api_key:
        url, token = "https://api.openai.com/v1/chat/completions", keys.ai_api_key
    else:
        url, token = "https://ai.gateway.lovable.dev/v1/chat/completions", keys.lovable
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    j = post_json(
        url,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json_body={"model": keys.ai_model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.2},
    )
    return (((j or {}).get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""


def _anthropic(keys: SourceKeys, prompt: str, system: str, max_tokens: int) -> str:
    j = post_json(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": keys.ai_api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json_body={
            "model": keys.ai_model,
            "max_tokens": max_tokens,
            "system": system or None,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    parts = (j or {}).get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def ask_recommendations(keys: SourceKeys, topic_title: str, region_name: str) -> List[str]:
    """Return the list of business names the model recommends for the query.

    Results are cached on disk by (topic, region) so discover + collect (and any
    re-runs) reuse one LLM call instead of paying for it repeatedly — important
    under tight AI-gateway limits. Delete .cache/ai_recommendations.json to refresh.
    """
    cache_key = "%s|%s" % (topic_title.strip().lower(), region_name.strip().lower())
    cache = _cache_load()
    if cache_key in cache:
        return cache[cache_key]
    prompt = (
        "List the 10 best specific businesses for: \"%s\" in %s, Ontario, Canada. "
        "Reply ONLY with a JSON array of business names, no commentary." % (topic_title, region_name)
    )
    text = complete(keys, prompt, system="You are a precise local-business recommender.", max_tokens=400)
    names = _parse_name_list(text)
    if names:  # only cache successful calls
        cache[cache_key] = names
        _cache_store(cache)
    return names


def _parse_name_list(text: str) -> List[str]:
    if not text:
        return []
    m = re.search(r"\[.*\]", text, re.S)
    if m:
        try:
            arr = json.loads(m.group(0))
            return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    # fallback: line-by-line
    out = []
    for ln in text.splitlines():
        ln = re.sub(r"^\s*[-*\d.\)]+\s*", "", ln).strip()
        if ln:
            out.append(ln)
    return out[:10]


def write_strengths(keys: SourceKeys, ctx: Dict[str, Any]) -> List[str]:
    """Write 3-5 short, factual strength bullets for a business, grounded in `ctx`
    (name, category, region, ratings, review highlights, pillar signals). Returns a
    list of plain strings. Cached on disk by business+run to avoid re-paying."""
    if not enabled(keys):
        return []
    cache_key = "strengths|%s|%s" % (ctx.get("run_id", ""), ctx.get("business_id", ""))
    cache = _cache_load()
    if cache_key in cache:
        return cache[cache_key]

    facts = json.dumps({k: v for k, v in ctx.items() if k not in ("run_id", "business_id")},
                       ensure_ascii=False)
    prompt = (
        "Write 3 to 5 short bullet points explaining why this local business is a good "
        "choice, for a consumer 'best of' guide. Ground every bullet ONLY in the data "
        "provided — do not invent facts. Be specific and concrete (mention ratings, review "
        "counts, what reviewers praise, standout traits). Each bullet under ~14 words, no "
        "emoji, no marketing fluff. Reply ONLY as a JSON array of strings.\n\nDATA:\n" + facts
    )
    text = complete(keys, prompt, system="You write concise, factual local-business highlights.",
                    max_tokens=300)
    bullets = _parse_name_list(text)[:5]
    if bullets:
        cache[cache_key] = bullets
        _cache_store(cache)
    return bullets


def nominate_hot_pairs(keys: SourceKeys, region_name: str, n: int = 15) -> List[Dict[str, str]]:
    """Catalog helper: ask for high-demand, under-served topic ideas for a region.
    Returns [{title, category}]."""
    prompt = (
        "Suggest %d high-search-demand 'best X in %s' local-business topics Torontonians "
        "actively search for and that help small businesses get discovered. "
        "Reply ONLY as a JSON array of objects {\"title\": str, \"category\": str}. "
        "Categories: food, drink, nightlife, beauty, health, fitness, services, shopping, "
        "home, auto, family, pets." % (n, region_name)
    )
    text = complete(keys, prompt, system="You are a local SEO and market-demand analyst.", max_tokens=900)
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        return [{"title": str(o["title"]).strip(), "category": str(o.get("category", "food")).strip()}
                for o in arr if o.get("title")]
    except Exception:
        return []
