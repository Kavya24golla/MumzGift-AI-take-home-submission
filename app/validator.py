from __future__ import annotations

from difflib import SequenceMatcher
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.schemas import FinalResponse, Product, validate_final_response_business_rules


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "products.json"


def _load_catalog_map() -> Dict[str, Product]:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    products = [Product(**item) for item in raw]
    return {p.product_id: p for p in products}


def reasons_are_product_specific(recommendations: List[Any]) -> bool:
    reasons_are_specific = True

    reason_list: List[str] = []
    for rec in recommendations:
        reason = rec.reason_en if hasattr(rec, "reason_en") else rec.get("reason_en", "")
        reason_list.append(str(reason))

    # Check 1: no two reasons should be more than 60% similar
    for i in range(len(reason_list)):
        for j in range(i + 1, len(reason_list)):
            similarity = SequenceMatcher(None, reason_list[i], reason_list[j]).ratio()
            if similarity > 0.6:
                reasons_are_specific = False

    # Check 2: banned phrases must not appear
    banned = [
        "thoughtful pick",
        "sensory play and early interaction",
        "kind of gift parents",
        "practical value for gifting",
        "stays within",
    ]
    for reason in reason_list:
        for phrase in banned:
            if phrase.lower() in reason.lower():
                reasons_are_specific = False

    return reasons_are_specific


# Thin wrapper module for strict response validation.
def validate_response_payload(response_payload: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        response = FinalResponse.model_validate(response_payload)
        catalog = _load_catalog_map()
        validate_final_response_business_rules(response, catalog)
        if response.status == "success" and not reasons_are_product_specific(response.recommendations):
            raise ValueError("Reasons are not product-specific enough")
        return True, "valid"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
