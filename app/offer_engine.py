from __future__ import annotations

from typing import List, Optional, Set, Tuple

from app.schemas import OptionalAddon, Product


DISCOUNT_PERCENT = 10.0
MIN_ADDON_THRESHOLD = 20.0
BLOCKED_ADDON_TAGS = {
    "diaper",
    "refill",
    "pail",
    "wipes_refill",
    "laundry",
    "cleaning",
    "disposal",
    "liner",
}
GIFT_SUITABLE_CATEGORIES = {
    "toys",
    "books",
    "feeding",
    "skincare",
    "accessories",
    "clothing",
    "bath",
}


def _is_compatible(main_category: str, addon_category: str) -> bool:
    compatible_pairs = {
        ("toys", "toys"),
        ("feeding", "feeding"),
        ("toys", "books"),
        ("books", "toys"),
        ("skincare", "skincare"),
    }
    return (main_category, addon_category) in compatible_pairs


def _preferred_groups_for_main(main_product: Product) -> List[str]:
    tags = set(main_product.tags or [])
    if "doll" in tags or "soft_toy" in tags:
        return ["books", "accessories", "bags"]
    if main_product.category == "feeding":
        return ["bibs", "spoons", "bottles"]
    if main_product.category == "skincare":
        return ["skincare", "wipes"]
    if "educational" in tags:
        return ["books", "puzzles"]
    return []


def _addon_group(addon: Product) -> str:
    tags = set(addon.tags or [])
    name = addon.name_en.lower()
    if "book" in name or "book" in tags:
        return "books"
    if "bag" in name or "bag" in tags or "travel" in tags:
        return "bags"
    if "bib" in name or "bib" in tags:
        return "bibs"
    if "spoon" in name or "spoon" in tags:
        return "spoons"
    if "bottle" in name or "bottle" in tags:
        return "bottles"
    if "puzzle" in name or "puzzle" in tags:
        return "puzzles"
    if addon.category == "clothing":
        return "accessories"
    return addon.category


def _is_gift_suitable_addon(addon: Product) -> bool:
    tags = {str(tag).strip().lower() for tag in (addon.tags or [])}
    if tags.intersection(BLOCKED_ADDON_TAGS):
        return False

    # If catalog later includes a gift_suitable flag, honor it.
    gift_suitable_flag = bool(getattr(addon, "gift_suitable", False))
    addon_group = _addon_group(addon)
    return gift_suitable_flag or addon.category in GIFT_SUITABLE_CATEGORIES or addon_group in GIFT_SUITABLE_CATEGORIES


def build_offer_for_main(
    main_product: Product,
    catalog: List[Product],
    budget_aed: float,
    used_addon_ids: Optional[Set[str]] = None,
) -> Tuple[Optional[OptionalAddon], str]:
    used = used_addon_ids if used_addon_ids is not None else set()
    remaining_budget = round(budget_aed - main_product.price_aed, 2)
    if remaining_budget < MIN_ADDON_THRESHOLD:
        return None, "No bundle offer — budget fully used by main gift"

    compatible_candidates: List[Product] = []
    age_compatible_candidates: List[Product] = []
    preferred_groups = _preferred_groups_for_main(main_product)

    main_preferred_groups = _preferred_groups_for_main(main_product)

    for addon in catalog:
        if addon.product_id == main_product.product_id:
            continue
        if addon.product_id in used:
            continue
        if not _is_gift_suitable_addon(addon):
            continue
        if not addon.in_stock:
            continue
        if addon.price_aed > remaining_budget:
            continue
        if addon.age_max_months < 24:
            continue
        # Rule 1: age compatibility
        if not (addon.age_min_months <= (main_product.age_min_months + 6)):
            continue

        # For doll/soft_toy mains, prioritize relevant add-on groups.
        # For others, apply compatible pair rule.
        if main_preferred_groups:
            pass
        else:
            if not _is_compatible(main_product.category, addon.category):
                continue

        compatible_candidates.append(addon)
        age_compatible_candidates.append(addon)

    if not age_compatible_candidates:
        return None, "No suitable add-on found for this age group."

    preferred_candidates = [
        addon for addon in age_compatible_candidates if _addon_group(addon) in set(preferred_groups)
    ]
    pool = preferred_candidates if preferred_candidates else age_compatible_candidates

    addon = min(pool, key=lambda item: item.price_aed)
    used.add(addon.product_id)
    original_total = round(main_product.price_aed + addon.price_aed, 2)
    discounted_total = round(original_total * (1 - DISCOUNT_PERCENT / 100), 2)
    savings = round(original_total - discounted_total, 2)

    return (
        OptionalAddon(
            product_id=addon.product_id,
            name_en=addon.name_en,
            name_ar=addon.name_ar,
            price_aed=addon.price_aed,
            discount_percent=DISCOUNT_PERCENT,
            original_total_aed=original_total,
            discounted_total_aed=discounted_total,
            savings_aed=savings,
        ),
        "Bundle offer available",
    )
