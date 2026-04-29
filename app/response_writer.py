from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.schemas import Product, QueryUnderstanding


CATEGORY_BENEFITS = {
    "toys": {
        "en": "supports sensory exploration, soft-touch play, and early motor engagement",
        "ar": "تدعم الاستكشاف الحسي واللعب الآمن وتنمية الحركة المبكرة",
    },
    "feeding": {
        "en": "helps during the early feeding stage",
        "ar": "تساعد في مرحلة الإطعام الأولى",
    },
    "bath": {
        "en": "makes bath time easier and more comfortable for baby and parents",
        "ar": "تجعل وقت الاستحمام أسهل وأكثر راحة للطفل والأهل",
    },
    "clothing": {
        "en": "is useful for everyday comfort and easy gifting",
        "ar": "تفيد في الراحة اليومية وتصلح كهدية عملية",
    },
    "diapers": {
        "en": "is a practical essential for daily baby care",
        "ar": "تعد من الأساسيات العملية للعناية اليومية بالطفل",
    },
    "new_mom_care": {
        "en": "supports the mother during early baby-care routines",
        "ar": "تدعم الأم في روتين العناية المبكرة بالطفل",
    },
}

DOLL_INTENT_TAGS = {"doll", "dolls", "pretend_play", "role_play"}
DOLL_BENEFIT_EN = "supports pretend play, storytelling, and nurturing role-play"
DOLL_BENEFIT_AR = "تدعم اللعب التخيلي وتمثيل الأدوار ورواية القصص"


def _arabic_digits(value: int) -> str:
    return str(value).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def _age_label_en(age_months: Optional[int]) -> str:
    if age_months is None:
        return "young baby"
    if age_months % 12 == 0 and age_months >= 24:
        years = age_months // 12
        return f"{years}-year-old"
    return f"{age_months}-month-old"


def _age_label_ar(age_months: Optional[int]) -> str:
    if age_months is None:
        return "هذا العمر"
    if age_months % 12 == 0 and age_months >= 24:
        years = age_months // 12
        return f"{_arabic_digits(years)} سنوات"
    if age_months < 12:
        return f"{_arabic_digits(age_months)} أشهر"
    return f"{_arabic_digits(age_months)} شهراً"


def _budget_int(value: Optional[float]) -> int:
    if value is None:
        return 200
    return int(round(value))


def _benefit_for_product(product: Product) -> Dict[str, str]:
    tags = {str(tag).strip().lower() for tag in (product.tags or [])}
    if tags.intersection(DOLL_INTENT_TAGS):
        return {"en": DOLL_BENEFIT_EN, "ar": DOLL_BENEFIT_AR}
    return CATEGORY_BENEFITS.get(product.category, CATEGORY_BENEFITS["toys"])


def _build_reason_pair(product: Product, query_understanding: QueryUnderstanding) -> Dict[str, str]:
    benefit = _benefit_for_product(product)
    age_en = _age_label_en(query_understanding.age_months)
    age_ar = _age_label_ar(query_understanding.age_months)
    budget = _budget_int(query_understanding.budget_aed)
    budget_ar = _arabic_digits(budget)

    tags = {str(tag).strip().lower() for tag in (product.tags or [])}
    if tags.intersection(DOLL_INTENT_TAGS) and query_understanding.age_months and query_understanding.age_months >= 24:
        reason_en = (
            f"{product.name_en} is a strong gift for a {age_en} who likes dolls because it {benefit['en']}. "
            f"It stays within the {budget} AED budget."
        )
        reason_ar = (
            f"{product.name_ar} هدية مناسبة لطفل بعمر {age_ar} يحب الدمى، لأنها {benefit['ar']}، "
            f"وتبقى ضمن ميزانية {budget_ar} درهم."
        )
    else:
        reason_en = (
            f"{product.name_en} is a strong gift for a {age_en} because it {benefit['en']}. "
            f"It stays within the {budget} AED budget."
        )
        reason_ar = (
            f"{product.name_ar} مناسبة لطفل بعمر {age_ar} لأنها {benefit['ar']}، "
            f"وتبقى ضمن ميزانية {budget_ar} درهم."
        )

    return {"reason_en": reason_en, "reason_ar": reason_ar}


def generate_reasons_for_products(
    products: Sequence[Product], query_understanding: QueryUnderstanding
) -> List[Dict[str, str]]:
    return [_build_reason_pair(product, query_understanding) for product in products]


def generate_response(query: str) -> Dict[str, Any]:
    from app.pipeline import run_pipeline

    return run_pipeline(query)
