from __future__ import annotations

from typing import Any, List, Optional, Set, Tuple

from app.schemas import BundleRelevance, OptionalAddon, Product
from app.semantic_bundle import BUNDLE_SCORE_THRESHOLD, find_semantic_addon


DISCOUNT_PERCENT = 10.0
MIN_ADDON_THRESHOLD = 20.0


def build_offer_for_main(
    main_product: Product,
    catalog: List[Product],
    query_understanding: Any,
    budget_aed: float,
    used_addon_ids: Optional[Set[str]] = None,
    raw_query: str = "",
    exclude_product_ids: Optional[Set[str]] = None,
) -> Tuple[Optional[OptionalAddon], str]:
    used = used_addon_ids if used_addon_ids is not None else set()

    remaining_budget = round(budget_aed - main_product.price_aed, 2)
    if remaining_budget < MIN_ADDON_THRESHOLD:
        return None, "No suitable add-on found for this intent."

    intent_payload: Any = query_understanding
    if hasattr(query_understanding, "model_dump"):
        intent_payload = query_understanding.model_dump()
    elif isinstance(query_understanding, dict):
        intent_payload = dict(query_understanding)
    if isinstance(intent_payload, dict):
        intent_payload["raw_query"] = raw_query

    addon_product, bundle_meta = find_semantic_addon(
        main_product=main_product,
        all_products=catalog,
        user_intent=intent_payload,
        budget_aed=budget_aed,
        used_addon_ids=used,
        exclude_product_ids=exclude_product_ids,
        threshold=BUNDLE_SCORE_THRESHOLD,
    )
    if addon_product is None or bundle_meta is None:
        return None, "No suitable add-on found for this intent."

    used.add(addon_product.product_id)
    original_total = round(main_product.price_aed + addon_product.price_aed, 2)
    discounted_total = round(original_total * (1 - DISCOUNT_PERCENT / 100), 2)
    savings = round(original_total - discounted_total, 2)

    if discounted_total > budget_aed:
        return None, "No suitable add-on found for this intent."

    addon = OptionalAddon(
        product_id=addon_product.product_id,
        name_en=addon_product.name_en,
        name_ar=addon_product.name_ar,
        price_aed=addon_product.price_aed,
        discount_percent=DISCOUNT_PERCENT,
        original_total_aed=original_total,
        discounted_total_aed=discounted_total,
        savings_aed=savings,
        bundle_relevance=BundleRelevance(**bundle_meta),
    )
    return addon, "Bundle offer available"
