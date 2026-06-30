"""Map a topic to the Google Places (New) `primaryType`s it is actually about,
so discovery keeps real cafés/barbers/etc. and drops the museums, universities,
hospitals, parks, and transit stations that big text searches drag in.

`target_types(title, category)` returns the acceptable types for a topic (empty
set = "no strict target, fall back to the denylist"). `accept(...)` is the per-
candidate decision used by discover.py.
"""

from __future__ import annotations

from typing import Optional, Set

# Broad food/drink family — the fallback for any food/drink/nightlife topic.
FOOD_TYPES: Set[str] = {
    "restaurant", "cafe", "coffee_shop", "bakery", "bar", "pub", "wine_bar",
    "meal_takeaway", "meal_delivery", "fast_food_restaurant", "sandwich_shop",
    "ice_cream_shop", "dessert_shop", "donut_shop", "juice_shop", "tea_house",
    "brewery", "night_club", "banquet_hall", "food", "deli", "diner",
}

# Keyword (checked against the lowercased title) -> acceptable primary types.
# Multi-word keys are checked before single-word keys.
KEYWORD_TYPES = {
    "bubble tea": {"cafe", "tea_house", "coffee_shop"},
    "hair salon": {"hair_salon", "beauty_salon", "hair_care"},
    "fine dining": FOOD_TYPES,
    "ice cream": {"ice_cream_shop"},
    "driving school": {"driving_school", "school"},
    "driving instructor": {"driving_school", "school"},
    "wedding hall": {"banquet_hall", "event_venue", "wedding_venue"},
    "farmers market": {"market", "grocery_store"},
    "walk-in clinic": {"doctor", "hospital", "medical_clinic"},
    "auto detailing": {"car_repair", "car_wash"},
    "coffee": {"coffee_shop", "cafe", "bakery"},
    "espresso": {"coffee_shop", "cafe"},
    "roaster": {"coffee_shop", "cafe"},
    "pastry": {"bakery", "cafe"},
    "biscotti": {"bakery", "cafe"},
    "bakery": {"bakery"},
    "dessert": {"bakery", "dessert_shop", "ice_cream_shop", "cafe"},
    "gelato": {"ice_cream_shop"},
    "cheese": {"store", "grocery_store", "deli"},
    "brewery": {"brewery", "bar", "liquor_store"},
    "karaoke": {"karaoke", "bar", "night_club"},
    "barber": {"barber_shop", "hair_care"},
    "salon": {"hair_salon", "beauty_salon", "hair_care"},
    "spa": {"spa", "beauty_salon"},
    "yoga": {"yoga_studio", "gym"},
    "fitness": {"gym", "fitness_center"},
    "dentist": {"dentist"},
    "clinic": {"doctor", "hospital", "medical_clinic"},
    "daycare": {"child_care_agency", "preschool"},
    "mechanic": {"car_repair"},
    "plumber": {"plumber"},
    "electrician": {"electrician"},
    "locksmith": {"locksmith"},
    "mover": {"moving_company"},
    "moving": {"moving_company"},
    "groomer": {"pet_store", "veterinary_care", "pet_groomer"},
    "bookstore": {"book_store"},
    "vintage": {"store", "clothing_store", "thrift_store"},
    "hardware": {"hardware_store", "home_goods_store"},
}

FOOD_CATEGORIES = {"food", "drink", "nightlife"}

# Types that are essentially never the answer to a consumer "best X" topic in our
# catalog — dropped even when no specific target applies. (Note: hospital/doctor are
# NOT here, because clinic/dentist topics legitimately use them.)
DENY: Set[str] = {
    "museum", "tourist_attraction", "art_gallery", "park", "national_park",
    "subway_station", "transit_station", "train_station", "light_rail_station",
    "bus_station", "university", "library", "place_of_worship", "stadium",
    "city_hall", "local_government_office", "courthouse", "primary_school",
    "secondary_school", "airport", "parking",
}


_STOP = {"best", "in", "the", "of", "a", "and", "on", "shop", "store", "restaurant",
         "for", "your", "near", "me", "toronto", "ontario", "canada"}


def target_types(title: str, category: Optional[str]) -> Set[str]:
    low = (title or "").lower()
    for kw in sorted(KEYWORD_TYPES, key=len, reverse=True):
        if kw in low:
            return set(KEYWORD_TYPES[kw])
    if (category or "") in FOOD_CATEGORIES:
        return set(FOOD_TYPES)
    return set()


def topic_terms(title: str) -> Set[str]:
    """Distinctive words from a topic title, used to rescue businesses Google
    mis-types (e.g. a bakery typed 'condominium_complex' named 'O Biscotti').
    Drops the leading 'Best …' and the trailing 'in <region>'."""
    import re
    core = title or ""
    for p in ("Best ", "best "):
        if core.startswith(p):
            core = core[len(p):]
    if " in " in core:
        core = core.rsplit(" in ", 1)[0]
    toks = re.findall(r"[a-z0-9]+", core.lower())
    return {t for t in toks if len(t) >= 3 and t not in _STOP}


def _name_matches(name: Optional[str], terms: Set[str]) -> bool:
    if not name or not terms:
        return False
    import re
    name_toks = set(re.findall(r"[a-z0-9]+", name.lower()))
    return bool(name_toks & terms)


def is_food(title: str, category: Optional[str]) -> bool:
    t = target_types(title, category)
    return (category or "") in FOOD_CATEGORIES or t == FOOD_TYPES


def accept(primary_type: Optional[str], target: Set[str], food: bool,
           name: str = "", terms: Optional[Set[str]] = None) -> bool:
    """Decide whether a candidate's Google primaryType fits the topic.

    Hard-blocks institutional types (museum/park/etc.). Otherwise keeps on-target
    types, and *rescues* off-target results whose NAME matches the topic — Google
    frequently mis-types newer businesses (e.g. a biscotti shop tagged
    'condominium_complex'), and a name match is strong evidence of relevance."""
    if not primary_type:
        return True  # Yelp / AI / unresolved candidates — keep, they were relevance-sourced
    if primary_type in DENY and primary_type not in target:
        return False
    if target:
        if primary_type in target:
            return True
        if food and primary_type.endswith("_restaurant"):
            return True  # e.g. sushi_restaurant, ramen_restaurant
        if _name_matches(name, terms or set()):
            return True  # mis-typed but the name clearly matches the category
        return False
    return True  # no specific target, but passed the denylist
