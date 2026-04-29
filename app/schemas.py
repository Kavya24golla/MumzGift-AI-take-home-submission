from __future__ import annotations

from typing import Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ALLOWED_MISSING_FIELDS = {"age_months", "budget_aed", "recipient"}


class QueryUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["en", "ar"]
    recipient: Optional[str] = None
    age_months: Optional[int] = Field(default=None, ge=0, le=120)
    budget_aed: Optional[float] = Field(default=None, gt=0)
    occasion: Optional[str] = None
    preferences: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)

    @field_validator("missing_fields")
    @classmethod
    def validate_missing_fields(cls, value: List[str]) -> List[str]:
        invalid = [field for field in value if field not in ALLOWED_MISSING_FIELDS]
        if invalid:
            raise ValueError(f"Unsupported missing fields: {invalid}")
        return value

    @field_validator("preferences")
    @classmethod
    def validate_preferences(cls, value: List[str]) -> List[str]:
        lowered = [item.strip().lower() for item in value if item and item.strip()]
        if "gift" in lowered or "هدية" in lowered:
            raise ValueError("preferences must not contain generic gift terms")
        # Preserve order while removing duplicates and blanks.
        return list(dict.fromkeys(lowered))


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    name_en: str
    name_ar: str
    category: Literal["toys", "feeding", "bath", "diapers", "clothing", "new_mom_care"]
    price_aed: float = Field(gt=0)
    age_min_months: int = Field(ge=0)
    age_max_months: int = Field(ge=0)
    tags: List[str] = Field(default_factory=list)
    in_stock: bool

    @model_validator(mode="after")
    def validate_age_range(self) -> "Product":
        if self.age_min_months > self.age_max_months:
            raise ValueError("age_min_months must be <= age_max_months")
        return self


class OptionalAddon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    name_en: str
    name_ar: str
    price_aed: float = Field(gt=0)
    discount_percent: float = Field(gt=0, le=100)
    original_total_aed: float = Field(gt=0)
    discounted_total_aed: float = Field(gt=0)
    savings_aed: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_discount_math(self) -> "OptionalAddon":
        expected_discounted = round(self.original_total_aed * (1 - self.discount_percent / 100), 2)
        expected_savings = round(self.original_total_aed - expected_discounted, 2)

        if round(self.discounted_total_aed, 2) != expected_discounted:
            raise ValueError("discount math is wrong: discounted_total_aed is invalid")
        if round(self.savings_aed, 2) != expected_savings:
            raise ValueError("discount math is wrong: savings_aed is invalid")
        return self


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_product: Product
    optional_addon: Optional[OptionalAddon] = None
    reason_en: str
    reason_ar: str
    confidence: float = Field(ge=0, le=1)

    @field_validator("reason_en", "reason_ar")
    @classmethod
    def validate_non_empty_reasons(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Reason text must not be empty")
        return value.strip()


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_respected: bool
    age_respected: bool
    all_products_in_stock: bool
    no_hallucinated_product_ids: bool
    arabic_output_present: bool
    discount_math_correct: bool


class FinalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "needs_clarification", "no_valid_match", "out_of_scope"]
    query_understanding: Optional[QueryUnderstanding] = None
    recommendations: List[Recommendation] = Field(default_factory=list, max_length=3)
    missing_fields: List[str] = Field(default_factory=list)
    question_en: Optional[str] = None
    question_ar: Optional[str] = None
    reason_en: Optional[str] = None
    reason_ar: Optional[str] = None
    validation: Optional[ValidationResult] = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "FinalResponse":
        if self.status == "success":
            if self.query_understanding is None:
                raise ValueError("query_understanding is required for success")
            if not self.recommendations:
                raise ValueError("At least one recommendation is required for success")
            if self.validation is None:
                raise ValueError("validation is required for success")
        elif self.status == "needs_clarification":
            if not self.missing_fields:
                raise ValueError("missing_fields are required for needs_clarification")
            if not self.question_en or not self.question_ar:
                raise ValueError("Bilingual clarification questions are required")
        elif self.status in {"no_valid_match", "out_of_scope"}:
            if not self.reason_en or not self.reason_ar:
                raise ValueError("Bilingual reasons are required for non-success responses")
        return self


def validate_final_response_business_rules(
    response: FinalResponse, catalog_products: Sequence[Product] | Dict[str, Product]
) -> FinalResponse:
    if response.status != "success":
        return response

    if isinstance(catalog_products, dict):
        catalog_by_id = catalog_products
    else:
        catalog_by_id = {product.product_id: product for product in catalog_products}

    query = response.query_understanding
    if query is None or query.budget_aed is None:
        raise ValueError("Success responses must include budget_aed")

    for rec in response.recommendations:
        main = rec.main_product
        if main.product_id not in catalog_by_id:
            raise ValueError(f"Hallucinated product_id: {main.product_id}")

        source_main = catalog_by_id[main.product_id]
        if not source_main.in_stock or not main.in_stock:
            raise ValueError(f"Out-of-stock product in recommendation: {main.product_id}")
        if main.price_aed > query.budget_aed:
            raise ValueError(f"Product over budget: {main.product_id}")
        if query.age_months is not None and not (main.age_min_months <= query.age_months <= main.age_max_months):
            raise ValueError(f"Age mismatch for product: {main.product_id}")
        if not rec.reason_ar.strip():
            raise ValueError("Arabic output is empty")

        if main.name_en != source_main.name_en or main.name_ar != source_main.name_ar:
            raise ValueError(f"Product name mismatch for {main.product_id}")

        addon = rec.optional_addon
        if addon is not None:
            if addon.product_id not in catalog_by_id:
                raise ValueError(f"Hallucinated add-on product_id: {addon.product_id}")
            source_addon = catalog_by_id[addon.product_id]
            if not source_addon.in_stock:
                raise ValueError(f"Out-of-stock add-on: {addon.product_id}")

            expected_original = round(main.price_aed + addon.price_aed, 2)
            expected_discounted = round(expected_original * 0.9, 2)
            expected_savings = round(expected_original - expected_discounted, 2)

            if round(addon.original_total_aed, 2) != expected_original:
                raise ValueError("discount math is wrong: original_total_aed is invalid")
            if round(addon.discounted_total_aed, 2) != expected_discounted:
                raise ValueError("discount math is wrong: discounted_total_aed is invalid")
            if round(addon.savings_aed, 2) != expected_savings:
                raise ValueError("discount math is wrong: savings_aed is invalid")
            if addon.discounted_total_aed > query.budget_aed:
                raise ValueError("Add-on offer is not safe: discounted total exceeds budget")

    return response
