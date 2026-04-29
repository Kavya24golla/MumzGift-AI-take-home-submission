from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas import Product
from app.semantic_search import product_to_semantic_text, semantic_similarity


BUNDLE_SCORE_THRESHOLD = 0.45
DISCOUNT_PERCENT = 10.0

SEMANTIC_GROUP_DESCRIPTIONS: Dict[str, str] = {
    "sensory_play": "Products for babies that support sensory exploration, textures, sounds, rattles, soft toys, teething, early motor play, and tummy-time play.",
    "pretend_play": "Products for toddlers and children that support dolls, role play, storytelling, pretend caregiving, imagination, and social play.",
    "feeding_support": "Products for baby feeding, spoons, bowls, bibs, bottles, sippy cups, bottle cleaning, and mealtime routines.",
    "bath_care": "Products for bath time, towels, sponges, bath toys, wash items, and baby hygiene.",
    "diapering": "Products for diapers, wipes, diaper cream, changing mats, and daily diaper care.",
    "clothing_comfort": "Products for socks, blankets, bibs, clothing, soft wear, and everyday comfort.",
    "books_learning": "Products for cloth books, story books, early learning, language, and parent-child reading.",
    "new_mom_care": "Products for mother care, recovery, comfort, and postpartum self-care.",
}


def assign_semantic_group(product: Product) -> str:
    tags = {str(tag).strip().lower() for tag in (product.tags or [])}
    if product.category == "feeding":
        return "feeding_support"
    if product.category == "bath":
        return "bath_care"
    if product.category == "diapers":
        return "diapering"
    if product.category == "clothing":
        return "clothing_comfort"
    if product.category == "new_mom_care":
        return "new_mom_care"
    if product.category == "toys":
        sensory_tags = {"soft", "sensory", "rattle", "teether", "motor", "baby", "play"}
        pretend_tags = {"doll", "dolls", "pretend_play", "role_play", "storytelling"}
        if product.age_max_months <= 24 and tags.intersection(sensory_tags):
            return "sensory_play"
        if product.age_min_months >= 24 and tags.intersection(pretend_tags):
            return "pretend_play"
        if tags.intersection({"story_book", "book", "educational"}):
            return "books_learning"
        # fall through to semantic choice within toy-family groups

    product_text = product_to_semantic_text(product)
    best_group = "sensory_play"
    best_score = -1.0
    allowed_groups = (
        {"sensory_play", "pretend_play", "books_learning"}
        if product.category == "toys"
        else set(SEMANTIC_GROUP_DESCRIPTIONS.keys())
    )
    for group, description in SEMANTIC_GROUP_DESCRIPTIONS.items():
        if group not in allowed_groups:
            continue
        score = semantic_similarity(product_text, description)
        if score > best_score:
            best_score = score
            best_group = group
    return best_group


def _intent_text(user_intent: Any) -> str:
    if isinstance(user_intent, str):
        return user_intent
    if user_intent is None:
        return ""

    if hasattr(user_intent, "model_dump"):
        payload = user_intent.model_dump()
    elif isinstance(user_intent, dict):
        payload = user_intent
    else:
        payload = {}

    raw_query = str(payload.get("raw_query", "") or "").strip()
    language = str(payload.get("language", "") or "")
    occasion = str(payload.get("occasion", "") or "")
    prefs = [str(item) for item in (payload.get("preferences", []) or [])]
    recipient = str(payload.get("recipient", "") or "")
    age = payload.get("age_months", "")
    return " ".join(
        part
        for part in [
            raw_query,
            f"language {language}",
            f"occasion {occasion}",
            f"recipient {recipient}",
            f"age {age} months" if age not in ("", None) else "",
            "preferences " + " ".join(prefs) if prefs else "",
        ]
        if part
    )


def _age_bonus(main_product: Product, addon: Product, user_age: Optional[int]) -> float:
    overlap = addon.age_min_months <= main_product.age_max_months and addon.age_max_months >= main_product.age_min_months
    if not overlap:
        return 0.0
    if user_age is None:
        return 0.7
    return 1.0 if addon.age_min_months <= user_age <= addon.age_max_months else 0.0


def _budget_bonus(main_price: float, addon_price: float, budget_aed: float) -> float:
    original = main_price + addon_price
    discounted = original * (1 - DISCOUNT_PERCENT / 100)
    if discounted > budget_aed:
        return 0.0
    slack = max(0.0, budget_aed - discounted)
    if budget_aed <= 0:
        return 1.0
    return max(0.4, 1.0 - min(0.6, slack / budget_aed))


def find_semantic_addon(
    main_product: Product,
    all_products: List[Product],
    user_intent: Any,
    budget_aed: float,
    used_addon_ids: Optional[Set[str]] = None,
    exclude_product_ids: Optional[Set[str]] = None,
    threshold: float = BUNDLE_SCORE_THRESHOLD,
) -> Tuple[Optional[Product], Optional[Dict[str, Any]]]:
    used = used_addon_ids if used_addon_ids is not None else set()
    excluded = exclude_product_ids if exclude_product_ids is not None else set()
    user_text = _intent_text(user_intent)
    main_text = product_to_semantic_text(main_product)
    main_group = assign_semantic_group(main_product)
    user_age: Optional[int] = None
    if hasattr(user_intent, "age_months"):
        user_age = getattr(user_intent, "age_months", None)
    elif isinstance(user_intent, dict):
        raw_age = user_intent.get("age_months")
        if isinstance(raw_age, (int, float)):
            user_age = int(raw_age)

    best: Optional[Product] = None
    best_meta: Optional[Dict[str, Any]] = None
    best_score = -1.0

    for addon in all_products:
        if addon.product_id == main_product.product_id:
            continue
        if addon.product_id in used:
            continue
        if addon.product_id in excluded:
            continue
        if not addon.in_stock:
            continue

        addon_text = product_to_semantic_text(addon)
        addon_group = assign_semantic_group(addon)

        age_bonus = _age_bonus(main_product, addon, user_age)
        if age_bonus <= 0:
            continue

        budget_bonus = _budget_bonus(main_product.price_aed, addon.price_aed, budget_aed)
        if budget_bonus <= 0:
            continue

        semantic_score = semantic_similarity(main_text, addon_text)
        query_alignment = semantic_similarity(user_text, addon_text) if user_text else 0.0
        group_bonus = 1.0 if main_group == addon_group else 0.0
        same_group = main_group == addon_group
        age_budget_stock_bonus = min(1.0, (age_bonus + budget_bonus + group_bonus) / 3.0)

        final_score = (
            0.65 * semantic_score
            + 0.25 * query_alignment
            + 0.10 * age_budget_stock_bonus
        )

        compatible = same_group or (semantic_score >= threshold) or (query_alignment >= threshold)
        if not compatible:
            continue
        if not (query_alignment > 0.15 or same_group):
            continue
        if final_score < threshold:
            continue

        if final_score > best_score:
            best_score = final_score
            best = addon
            reason_map = {
                "sensory_play": "Both products support sensory play and early motor exploration for this age group.",
                "pretend_play": "Both products support pretend play, storytelling, and role-play.",
                "feeding_support": "Both products support feeding routines and mealtime use.",
                "bath_care": "Both products support bath-time comfort and care.",
            }
            reason = reason_map.get(
                main_group,
                "Both products are semantically aligned with the gifting intent.",
            )
            best_meta = {
                "semantic_group_main": main_group,
                "semantic_group_addon": addon_group,
                "semantic_similarity": round(float(semantic_score), 4),
                "query_alignment": round(float(query_alignment), 4),
                "final_bundle_score": round(float(final_score), 4),
                "reason": reason,
            }

    return best, best_meta
