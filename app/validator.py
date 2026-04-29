from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.schemas import FinalResponse, Product, validate_final_response_business_rules
from app.semantic_bundle import BUNDLE_SCORE_THRESHOLD


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "products.json"


def _load_catalog_map() -> Dict[str, Product]:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    products = [Product(**item) for item in raw]
    return {p.product_id: p for p in products}


def reasons_are_product_specific(recommendations: List[Any]) -> bool:
    category_benefit_words = {
        "toys": [
            "sensory exploration",
            "soft-touch play",
            "motor engagement",
            "pretend play",
            "storytelling",
            "role-play",
        ],
        "feeding": ["early feeding stage", "feeding stage"],
        "bath": ["bath time easier", "more comfortable for baby and parents"],
        "clothing": ["everyday comfort", "easy gifting"],
        "diapers": ["practical essential", "daily baby care"],
        "new_mom_care": ["supports the mother", "baby-care routines"],
    }
    category_benefit_words_ar = {
        "toys": "يدعم الاستكشاف الحسي واللعب الآمن وتنمية الحركة المبكرة",
        "feeding": "يساعد في مرحلة الإطعام الأولى",
        "bath": "يجعل وقت الاستحمام أسهل وأكثر راحة للطفل والأهل",
        "clothing": "مفيد للراحة اليومية ويصلح كهدية عملية",
        "diapers": "من الأساسيات العملية للعناية اليومية بالطفل",
        "new_mom_care": "يدعم الأم في روتين العناية المبكرة بالطفل",
    }
    banned_generic = [
        "matches what children need",
        "supports practical daily use",
        "suitable for this stage",
        "good choice",
        "practical value for gifting",
    ]

    for rec in recommendations:
        reason_en = rec.reason_en if hasattr(rec, "reason_en") else rec.get("reason_en", "")
        reason_ar = rec.reason_ar if hasattr(rec, "reason_ar") else rec.get("reason_ar", "")
        main_product = rec.main_product if hasattr(rec, "main_product") else rec.get("main_product", {})

        name_en = main_product.name_en if hasattr(main_product, "name_en") else main_product.get("name_en", "")
        name_ar = main_product.name_ar if hasattr(main_product, "name_ar") else main_product.get("name_ar", "")
        category = main_product.category if hasattr(main_product, "category") else main_product.get("category", "")

        en_text = str(reason_en or "")
        ar_text = str(reason_ar or "")
        en_lower = en_text.lower()

        if not name_en or name_en.lower() not in en_lower:
            return False

        expected_words = category_benefit_words.get(str(category), [])
        if expected_words and not any(word in en_lower for word in expected_words):
            return False

        if not ar_text.strip():
            return False

        expected_ar = category_benefit_words_ar.get(str(category), "")
        if name_ar not in ar_text and (expected_ar and expected_ar not in ar_text):
            return False

        mentions_age_or_budget = bool(
            re.search(r"\b\d+\s*[- ]?month|\b\d+\s*AED|\bbudget\b", en_text, flags=re.IGNORECASE)
            or re.search(r"(درهم|ميزانية|شهر|أشهر|شهراً|سنة|سنوات|[٠-٩])", ar_text)
        )
        if not mentions_age_or_budget:
            return False

        for phrase in banned_generic:
            if phrase in en_lower:
                return False

    return True


# Thin wrapper module for strict response validation.
def validate_response_payload(response_payload: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        response = FinalResponse.model_validate(response_payload)
        catalog = _load_catalog_map()
        validate_final_response_business_rules(response, catalog)
        if response.status == "success":
            main_ids = {rec.main_product.product_id for rec in response.recommendations}
            for rec in response.recommendations:
                addon = rec.optional_addon
                if addon is None:
                    continue
                if addon.bundle_relevance.final_bundle_score < BUNDLE_SCORE_THRESHOLD:
                    raise ValueError("bundle_relevance is below semantic threshold")
                if addon.product_id in main_ids:
                    raise ValueError("bundle_relevance failed: add-on duplicates a main recommendation")
                same_group = addon.bundle_relevance.semantic_group_main == addon.bundle_relevance.semantic_group_addon
                if not (addon.bundle_relevance.query_alignment > 0.15 or same_group):
                    raise ValueError("bundle_relevance failed: low query alignment without group match")
        if response.status == "success" and not reasons_are_product_specific(response.recommendations):
            raise ValueError("Reasons are not product-specific enough")
        return True, "valid"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
