from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from app.catalog_search import rank_products
from app.offer_engine import build_offer_for_main
from app.query_extractor import extract_query_understanding
from app.response_writer import generate_reasons_for_products
from app.semantic_search import SemanticProductSearch
from app.semantic_bundle import BUNDLE_SCORE_THRESHOLD
from app.schemas import (
    FinalResponse,
    OptionalAddon,
    Product,
    QueryUnderstanding,
    Recommendation,
    ValidationResult,
    validate_final_response_business_rules,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "products.json"
MAX_RECOMMENDATIONS = 3
BUNDLE_DISCOUNT_PERCENT = 10.0

_SEMANTIC_SEARCH: Optional[SemanticProductSearch] = None
_SEMANTIC_SIGNATURE: tuple[str, ...] = ()

load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.local")

_AR_REASON_TEMPLATES = {
    "toys": [
        "بهالعمر، اللعب الحسي يفرق كثير، و{name_ar} يساعد الطفل يتفاعل مع الملمس والحركة.",
        "{name_ar} يعطي الطفل بعمر {age} أشهر وقت لعب ممتع ويقوي تركيزه خطوة خطوة.",
        "للأعمار حول {age} أشهر، {name_ar} خيار حلو لأنه يجمع المتعة مع تنمية المهارات المبكرة.",
    ],
    "feeding": [
        "مرحلة {age} أشهر غالبًا تكون بداية أكل فعلي، و{name_ar} يسهل الإطعام على الأم والطفل.",
        "مع دخول عمر {age} أشهر، {name_ar} يفيد في الوجبات اليومية ويخفف الفوضى وقت الأكل.",
        "{name_ar} مناسب لهالعمر لأنه يدعم الاستقلالية البسيطة وقت الإطعام بطريقة مريحة.",
    ],
    "bath": [
        "{name_ar} يجعل وقت الحمام أريح للأم والبيبي، خصوصًا بعمر {age} أشهر.",
        "بهالمرحلة، روتين الحمام مهم جدًا، و{name_ar} يساعد يكون الوقت أسهل وأكثر راحة.",
        "{name_ar} هدية موفقة لعمر {age} أشهر لأنه يخدم احتياج يومي فعلي وقت الاستحمام.",
    ],
    "diapers": [
        "{name_ar} من أكثر الأشياء اللي تنفع يوميًا مع البيبي بعمر {age} أشهر.",
        "احتياجات الحفاض ما توقف بهالعمر، و{name_ar} يساعد الأهل بشكل مباشر كل يوم.",
        "كهدية لعمر {age} أشهر، {name_ar} خيار ذكي لأنه يخدم العناية اليومية فعليًا.",
    ],
    "clothing": [
        "{name_ar} مناسب لعمر {age} أشهر لأن الراحة بالحركة واللبس تصير أهم بهالمرحلة.",
        "الملابس المريحة مثل {name_ar} تكون هدية محبوبة فعلًا للأهل والطفل بهالعمر.",
        "بعمر {age} أشهر، {name_ar} خيار عملي ينعاد استخدامه كثير خلال الأسبوع.",
    ],
    "new_mom_care": [
        "مع طفل بعمر {age} أشهر، {name_ar} يعطي دعم مفيد للأم في يومها.",
        "{name_ar} هدية جميلة للأم الجديدة لأنها تخفف ضغط المرحلة وتضيف راحة حقيقية.",
        "بهالفترة، العناية بالأم مهمة مثل عناية الطفل، و{name_ar} يخدم هالاحتياج بشكل واضح.",
    ],
}


def _load_catalog() -> List[Product]:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return [Product(**item) for item in raw]


def _get_semantic_search(catalog: List[Product]) -> SemanticProductSearch:
    global _SEMANTIC_SEARCH, _SEMANTIC_SIGNATURE
    signature = tuple(product.product_id for product in catalog)
    if _SEMANTIC_SEARCH is None or signature != _SEMANTIC_SIGNATURE:
        _SEMANTIC_SEARCH = SemanticProductSearch(catalog)
        _SEMANTIC_SIGNATURE = signature
    return _SEMANTIC_SEARCH


def _preferred_categories(query_understanding: QueryUnderstanding) -> List[str]:
    category_labels = {"toys", "feeding", "bath", "diapers", "clothing", "new_mom_care"}
    return [pref for pref in query_understanding.preferences if pref in category_labels]


def _is_out_of_scope(query_understanding: QueryUnderstanding) -> bool:
    return query_understanding.recipient == "adult"


def _score_product(product: Product, query_understanding: QueryUnderstanding, categories: List[str]) -> float:
    score = 0.0
    query_prefs = set(query_understanding.preferences)
    product_tags = set(product.tags or [])

    if categories and product.category in categories:
        score += 3.0
    elif categories:
        score -= 1.0

    if "thoughtful" in query_prefs and "thoughtful" in product_tags:
        score += 1.0
    if "useful" in query_prefs and "useful" in product_tags:
        score += 1.0
    if "organic" in query_prefs and "organic" in product_tags:
        score += 0.8
    if "soft" in query_prefs and "soft" in product_tags:
        score += 0.8

    return score


def _build_validation_flags(
    recommendations: List[Recommendation],
    query_understanding: QueryUnderstanding,
    catalog_by_id: Dict[str, Product],
    main_recommendation_ids: set[str],
) -> ValidationResult:
    budget = query_understanding.budget_aed
    age = query_understanding.age_months

    budget_ok = True
    age_ok = True
    stock_ok = True
    ids_ok = True
    ar_ok = True
    discount_ok = True
    bundle_relevance_ok = True

    for rec in recommendations:
        main = rec.main_product
        if main.product_id not in catalog_by_id:
            ids_ok = False
            continue
        src = catalog_by_id[main.product_id]
        if budget is not None and main.price_aed > budget:
            budget_ok = False
        if age is not None and not (main.age_min_months <= age <= main.age_max_months):
            age_ok = False
        if not src.in_stock or not main.in_stock:
            stock_ok = False
        if not rec.reason_ar.strip():
            ar_ok = False

        addon = rec.optional_addon
        if addon:
            if addon.product_id not in catalog_by_id:
                ids_ok = False
            else:
                if not catalog_by_id[addon.product_id].in_stock:
                    stock_ok = False
                if query_understanding.age_months is not None and not (
                    catalog_by_id[addon.product_id].age_min_months
                    <= query_understanding.age_months
                    <= catalog_by_id[addon.product_id].age_max_months
                ):
                    age_ok = False
            if addon.product_id in main_recommendation_ids:
                bundle_relevance_ok = False
            if addon.bundle_relevance.final_bundle_score < BUNDLE_SCORE_THRESHOLD:
                bundle_relevance_ok = False
            same_group = addon.bundle_relevance.semantic_group_main == addon.bundle_relevance.semantic_group_addon
            if not (addon.bundle_relevance.query_alignment > 0.15 or same_group):
                bundle_relevance_ok = False
            expected_discounted = round(addon.original_total_aed * (1 - addon.discount_percent / 100), 2)
            if round(addon.discounted_total_aed, 2) != expected_discounted:
                discount_ok = False

    return ValidationResult(
        budget_respected=budget_ok,
        age_respected=age_ok,
        all_products_in_stock=stock_ok,
        no_hallucinated_product_ids=ids_ok,
        arabic_output_present=ar_ok,
        discount_math_correct=discount_ok,
        bundle_relevance=bundle_relevance_ok,
    )


def _semantic_rank_score(
    product: Product,
    semantic_score: float,
    query_understanding: QueryUnderstanding,
    preferred_categories: List[str],
) -> float:
    score = semantic_score

    if preferred_categories and product.category in preferred_categories:
        score += 0.12
    elif query_understanding.occasion == "gift" and "gift" in set(product.tags or []):
        score += 0.05

    pref_matches = len(set(query_understanding.preferences).intersection(set(product.tags or [])))
    score += min(0.18, pref_matches * 0.06)

    return score


def run_pipeline(query: str) -> dict:
    catalog = _load_catalog()
    catalog_by_id = {product.product_id: product for product in catalog}
    understanding = extract_query_understanding(query)

    if _is_out_of_scope(understanding):
        response = FinalResponse(
            status="out_of_scope",
            query_understanding=understanding,
            reason_en="This assistant currently supports baby and new-mom gifting only.",
            reason_ar="هذا المساعد مخصص لهدايا الأطفال والأم الجديدة فقط.",
        )
        return response.model_dump()

    missing_for_decision: List[str] = []
    if understanding.age_months is None and not understanding.preferences:
        missing_for_decision.append("age_months")
    if understanding.budget_aed is None:
        missing_for_decision.append("budget_aed")

    if missing_for_decision:
        response = FinalResponse(
            status="needs_clarification",
            query_understanding=understanding,
            missing_fields=missing_for_decision,
            question_en="What is the baby's age and your budget?",
            question_ar="ما عمر الطفل وما الميزانية المناسبة؟",
        )
        return response.model_dump()

    assert understanding.budget_aed is not None

    preferred_categories = _preferred_categories(understanding)
    semantic_engine = _get_semantic_search(catalog)
    semantic_results = semantic_engine.search(query, top_k=20)
    if not semantic_results:
        semantic_results = [{"product": product, "semantic_score": 0.0, "search_text": ""} for product in catalog]

    candidates: List[Product] = []
    semantic_scores: Dict[str, float] = {}

    def collect_filtered(results: List[Dict[str, object]]) -> None:
        for item in results:
            product = item["product"]
            if not isinstance(product, Product):
                continue
            if not product.in_stock:
                continue
            if product.price_aed > understanding.budget_aed:
                continue
            if understanding.age_months is not None and not (
                product.age_min_months <= understanding.age_months <= product.age_max_months
            ):
                continue
            if preferred_categories and product.category not in preferred_categories:
                continue

            if product.product_id not in semantic_scores:
                candidates.append(product)
            semantic_scores[product.product_id] = max(
                semantic_scores.get(product.product_id, 0.0), float(item.get("semantic_score", 0.0))
            )

    collect_filtered(semantic_results)
    if len(candidates) < MAX_RECOMMENDATIONS and len(semantic_results) < len(catalog):
        # Retry with a wider semantic candidate set when top-k is too narrow.
        semantic_results = semantic_engine.search(query, top_k=len(catalog))
        collect_filtered(semantic_results)

    if not candidates:
        age_part = (
            f"for age {understanding.age_months} months "
            if understanding.age_months is not None
            else ""
        )
        response = FinalResponse(
            status="no_valid_match",
            query_understanding=understanding,
            reason_en=(
                f"No in-stock product in the catalog fits {age_part}"
                f"under {int(understanding.budget_aed)} AED."
            ),
            reason_ar=(
                "لا يوجد منتج متوفر يطابق تفاصيل طلبك الحالي."
            ),
        )
        return response.model_dump()

    ranked = rank_products(
        candidates,
        understanding.budget_aed,
        score_fn=lambda product: (
            _semantic_rank_score(
                product,
                semantic_scores.get(product.product_id, 0.0),
                understanding,
                preferred_categories,
            )
            + _score_product(product, understanding, preferred_categories)
        ),
    )
    top = ranked[:MAX_RECOMMENDATIONS]
    generated_reasons = generate_reasons_for_products(top, understanding)
    used_addon_ids: set[str] = set()
    top_main_ids = {product.product_id for product in top}

    recommendations: List[Recommendation] = []
    for rank, main in enumerate(top):
        addon, _offer_reason = build_offer_for_main(
            main_product=main,
            catalog=catalog,
            query_understanding=understanding,
            budget_aed=understanding.budget_aed,
            used_addon_ids=used_addon_ids,
            raw_query=query,
            exclude_product_ids=top_main_ids,
        )
        reasons = generated_reasons[rank] if rank < len(generated_reasons) else {
            "reason_en": "Unable to generate reason.",
            "reason_ar": "تعذّر إنشاء السبب.",
        }
        confidence = max(0.55, round(0.9 - (rank * 0.1), 2))
        rec = Recommendation(
            main_product=main,
            optional_addon=addon,
            reason_en=reasons["reason_en"],
            reason_ar=reasons["reason_ar"],
            confidence=confidence,
        )
        recommendations.append(rec)

    recommended_main_ids = {rec.main_product.product_id for rec in recommendations}
    validation = _build_validation_flags(recommendations, understanding, catalog_by_id, recommended_main_ids)
    response = FinalResponse(
        status="success",
        query_understanding=understanding,
        recommendations=recommendations,
        validation=validation,
    )
    validate_final_response_business_rules(response, catalog_by_id)
    return response.model_dump()
