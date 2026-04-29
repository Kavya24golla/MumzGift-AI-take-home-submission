from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.pipeline import run_pipeline  # noqa: E402
from app.schemas import Product  # noqa: E402
from app.validator import validate_response_payload  # noqa: E402


PRODUCTS_PATH = ROOT_DIR / "data" / "products.json"
TEST_CASES_PATH = ROOT_DIR / "evals" / "test_cases.json"


CheckFn = Callable[[Dict[str, Any], Dict[str, Any], Dict[str, Product]], Tuple[bool, str]]


def load_catalog() -> Dict[str, Product]:
    with PRODUCTS_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    products = [Product(**item) for item in raw]
    return {p.product_id: p for p in products}


def load_test_cases() -> List[Dict[str, Any]]:
    with TEST_CASES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_recommendations(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    return response.get("recommendations", []) or []


def _case_budget(case: Dict[str, Any], response: Dict[str, Any]) -> Any:
    if case.get("max_main_product_price") is not None:
        return case["max_main_product_price"]
    return (response.get("query_understanding") or {}).get("budget_aed")


def _case_age(case: Dict[str, Any], response: Dict[str, Any]) -> Any:
    if case.get("expected_age_months") is not None:
        return case["expected_age_months"]
    return (response.get("query_understanding") or {}).get("age_months")


def check_status_correct(case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]) -> Tuple[bool, str]:
    expected = case.get("expected_status")
    actual = response.get("status")
    ok = actual == expected
    return ok, f"expected status={expected}, got {actual}"


def check_language_correct(case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]) -> Tuple[bool, str]:
    expected = case.get("expected_language")
    actual = (response.get("query_understanding") or {}).get("language")
    ok = actual == expected
    return ok, f"expected language={expected}, got {actual}"


def check_budget_respected(case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]) -> Tuple[bool, str]:
    recs = _get_recommendations(response)
    if not recs:
        return True, "no recommendations to validate"

    limit = _case_budget(case, response)
    if limit is None:
        return False, "no budget available"

    for rec in recs:
        main_price = (rec.get("main_product") or {}).get("price_aed")
        if main_price is None or float(main_price) > float(limit):
            return False, f"main product over budget ({main_price} > {limit})"
    return True, f"all main products <= {limit}"


def check_age_respected(case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]) -> Tuple[bool, str]:
    recs = _get_recommendations(response)
    if not recs:
        return True, "no recommendations to validate"

    expected_age = _case_age(case, response)
    if expected_age is None:
        return False, "no expected age available"

    for rec in recs:
        main = rec.get("main_product") or {}
        age_min = main.get("age_min_months")
        age_max = main.get("age_max_months")
        if age_min is None or age_max is None:
            return False, "missing age range in recommended product"
        if not (int(age_min) <= int(expected_age) <= int(age_max)):
            pid = main.get("product_id")
            return False, f"age mismatch for {pid}: {age_min}-{age_max} vs {expected_age}"
    return True, "all recommended products satisfy age range"


def check_stock_respected(_: Dict[str, Any], response: Dict[str, Any], catalog: Dict[str, Product]) -> Tuple[bool, str]:
    recs = _get_recommendations(response)
    for rec in recs:
        main = rec.get("main_product") or {}
        main_id = main.get("product_id")
        if not main_id or main_id not in catalog:
            return False, f"unknown main product id {main_id}"
        if not catalog[main_id].in_stock:
            return False, f"main product out of stock {main_id}"

        addon = rec.get("optional_addon")
        if addon:
            addon_id = addon.get("product_id")
            if not addon_id or addon_id not in catalog:
                return False, f"unknown add-on product id {addon_id}"
            if not catalog[addon_id].in_stock:
                return False, f"add-on out of stock {addon_id}"
    return True, "all recommended products are in stock"


def check_no_hallucinated_product_ids(
    _: Dict[str, Any], response: Dict[str, Any], catalog: Dict[str, Product]
) -> Tuple[bool, str]:
    recs = _get_recommendations(response)
    for rec in recs:
        main_id = (rec.get("main_product") or {}).get("product_id")
        if not main_id or main_id not in catalog:
            return False, f"hallucinated main product id {main_id}"
        addon = rec.get("optional_addon")
        if addon:
            addon_id = addon.get("product_id")
            if not addon_id or addon_id not in catalog:
                return False, f"hallucinated add-on product id {addon_id}"
    return True, "all product ids exist in catalog"


def check_arabic_output_present(
    case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]
) -> Tuple[bool, str]:
    status = response.get("status")
    if status == "success":
        for rec in _get_recommendations(response):
            reason_ar = rec.get("reason_ar", "")
            if not isinstance(reason_ar, str) or not reason_ar.strip():
                pid = (rec.get("main_product") or {}).get("product_id")
                return False, f"missing Arabic reason for {pid}"
        return True, "Arabic reasons are present"

    if status == "needs_clarification":
        question_ar = response.get("question_ar", "")
        ok = isinstance(question_ar, str) and bool(question_ar.strip())
        return ok, "Arabic clarification question is present"

    reason_ar = response.get("reason_ar", "")
    ok = isinstance(reason_ar, str) and bool(reason_ar.strip())
    return ok, f"Arabic reason present for status {case.get('expected_status')}"


def check_discount_math_correct(
    _: Dict[str, Any], response: Dict[str, Any], __: Dict[str, Product]
) -> Tuple[bool, str]:
    for rec in _get_recommendations(response):
        addon = rec.get("optional_addon")
        if not addon:
            continue
        discount_percent = float(addon.get("discount_percent", 0))
        original_total = float(addon.get("original_total_aed", 0))
        discounted_total = float(addon.get("discounted_total_aed", 0))
        savings = float(addon.get("savings_aed", 0))

        expected_discounted = round(original_total * (1 - discount_percent / 100), 2)
        expected_savings = round(original_total - expected_discounted, 2)
        if round(discounted_total, 2) != expected_discounted:
            return False, f"discounted total mismatch ({discounted_total} != {expected_discounted})"
        if round(savings, 2) != expected_savings:
            return False, f"savings mismatch ({savings} != {expected_savings})"
    return True, "discount math is correct"


def check_asks_clarifying_question(
    case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]
) -> Tuple[bool, str]:
    if response.get("status") != "needs_clarification":
        return False, f"status is {response.get('status')} instead of needs_clarification"

    q_en = response.get("question_en", "")
    q_ar = response.get("question_ar", "")
    missing = set(response.get("missing_fields", []))
    expected_missing = set(case.get("expected_missing_fields", []))
    has_questions = bool(str(q_en).strip()) and bool(str(q_ar).strip())
    has_missing = expected_missing.issubset(missing)
    ok = has_questions and has_missing
    return ok, f"questions_present={has_questions}, missing_fields_match={has_missing}"


def check_does_not_force_recommendation(
    case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]
) -> Tuple[bool, str]:
    recs = _get_recommendations(response)
    if case.get("expected_status") == "success":
        ok = len(recs) > 0
        return ok, "success case should include recommendations"
    ok = len(recs) == 0
    return ok, "non-success case should not include recommendations"


def check_category_relevant(
    case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]
) -> Tuple[bool, str]:
    preferred = set(case.get("preferred_categories", []))
    if not preferred:
        return True, "no preferred categories requested"

    recs = _get_recommendations(response)
    if not recs:
        return False, "no recommendations returned"

    for rec in recs:
        cat = (rec.get("main_product") or {}).get("category")
        if cat not in preferred:
            return False, f"irrelevant category {cat}, expected one of {sorted(preferred)}"
    return True, "all recommendations are category relevant"


def check_semantic_relevance(
    case: Dict[str, Any], response: Dict[str, Any], _: Dict[str, Product]
) -> Tuple[bool, str]:
    concepts = [str(item).lower() for item in case.get("expected_semantic_concepts", [])]
    if not concepts:
        return True, "no semantic concept constraints requested"

    recs = _get_recommendations(response)
    if not recs:
        return False, "no recommendations returned"

    hits = 0
    for rec in recs:
        main = rec.get("main_product") or {}
        search_text = " ".join(
            [
                str(main.get("name_en", "")),
                str(main.get("name_ar", "")),
                str(main.get("category", "")),
                " ".join(str(tag) for tag in (main.get("tags") or [])),
            ]
        ).lower()
        if any(concept in search_text for concept in concepts):
            hits += 1

    ok = hits > 0
    return ok, f"semantic concept overlap hits={hits}"


def check_no_recommendations_for_non_success(
    _: Dict[str, Any], response: Dict[str, Any], __: Dict[str, Product]
) -> Tuple[bool, str]:
    status = response.get("status")
    recs = _get_recommendations(response)
    if status in {"needs_clarification", "no_valid_match", "out_of_scope"}:
        ok = len(recs) == 0
        return ok, f"status={status} should not include recommendations"
    return True, "not applicable for success"


CHECK_HANDLERS: Dict[str, CheckFn] = {
    "status_correct": check_status_correct,
    "language_correct": check_language_correct,
    "budget_respected": check_budget_respected,
    "age_respected": check_age_respected,
    "stock_respected": check_stock_respected,
    "no_hallucinated_product_ids": check_no_hallucinated_product_ids,
    "arabic_output_present": check_arabic_output_present,
    "discount_math_correct": check_discount_math_correct,
    "asks_clarifying_question": check_asks_clarifying_question,
    "does_not_force_recommendation": check_does_not_force_recommendation,
    "category_relevant": check_category_relevant,
    "semantic_relevance": check_semantic_relevance,
}


def _has_recommendations(response: Dict[str, Any]) -> bool:
    return len(_get_recommendations(response)) > 0


def _has_any_addon(response: Dict[str, Any]) -> bool:
    for rec in _get_recommendations(response):
        if rec.get("optional_addon"):
            return True
    return False


def _budget_available(case: Dict[str, Any], response: Dict[str, Any]) -> bool:
    return _case_budget(case, response) is not None


def _age_available(case: Dict[str, Any], response: Dict[str, Any]) -> bool:
    return _case_age(case, response) is not None


FULL_SUITE_CHECKS: Dict[str, Tuple[CheckFn, Callable[[Dict[str, Any], Dict[str, Any]], bool]]] = {
    "no_hallucinated_product_ids": (check_no_hallucinated_product_ids, lambda _c, _r: True),
    "stock_respected": (check_stock_respected, lambda _c, _r: True),
    "arabic_output_present": (check_arabic_output_present, lambda _c, r: _has_recommendations(r)),
    "discount_math_correct": (check_discount_math_correct, lambda _c, r: _has_any_addon(r)),
    "budget_respected": (check_budget_respected, _budget_available),
    "age_respected": (check_age_respected, _age_available),
    "no_recommendations_for_non_success": (check_no_recommendations_for_non_success, lambda _c, _r: True),
}


def _find_success_response_with_addon(test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    for case in test_cases:
        response = run_pipeline(case["query"])
        if response.get("status") == "success" and _has_any_addon(response):
            return response
    fallback = run_pipeline("Gift for a 6-month-old baby under 200 AED")
    if fallback.get("status") == "success":
        return fallback
    raise RuntimeError("Could not generate a baseline success response for adversarial checks.")


def run_adversarial_checks(catalog: Dict[str, Product], test_cases: List[Dict[str, Any]]) -> Tuple[int, int, List[str]]:
    base = _find_success_response_with_addon(test_cases)
    failures: List[str] = []

    out_of_stock_product = next((p for p in catalog.values() if not p.in_stock), None)
    if out_of_stock_product is None:
        return 0, 0, ["No out-of-stock product found for adversarial test."]

    checks = []

    fake_id_payload = copy.deepcopy(base)
    fake_id_payload["recommendations"][0]["main_product"]["product_id"] = "P999_FAKE"
    checks.append(("fake product_id", fake_id_payload))

    out_of_stock_payload = copy.deepcopy(base)
    out_of_stock_payload["recommendations"][0]["main_product"] = out_of_stock_product.model_dump()
    checks.append(("out-of-stock product", out_of_stock_payload))

    empty_ar_payload = copy.deepcopy(base)
    empty_ar_payload["recommendations"][0]["reason_ar"] = "   "
    checks.append(("empty Arabic reason", empty_ar_payload))

    wrong_discount_payload = copy.deepcopy(base)
    first_addon = (wrong_discount_payload["recommendations"][0]).get("optional_addon")
    if first_addon:
        first_addon["discounted_total_aed"] = round(float(first_addon["discounted_total_aed"]) + 2, 2)
        checks.append(("wrong discount math", wrong_discount_payload))

    passed = 0
    total = len(checks)

    for label, payload in checks:
        ok, err = validate_response_payload(payload)
        if ok:
            failures.append(f"{label}: validator did not reject corrupted payload")
        else:
            passed += 1

    return passed, total, failures


def run_all_evals() -> int:
    catalog = load_catalog()
    test_cases = load_test_cases()

    required_counts: Dict[str, Dict[str, int]] = {metric: {"passed": 0, "total": 0} for metric in CHECK_HANDLERS.keys()}
    full_suite_counts: Dict[str, Dict[str, int]] = {
        metric: {"passed": 0, "total": 0} for metric in FULL_SUITE_CHECKS.keys()
    }

    required_failures: List[Tuple[str, str]] = []
    full_suite_failures: List[Tuple[str, str]] = []

    for case in test_cases:
        case_id = case["id"]
        response = run_pipeline(case["query"])

        # Layer A: Required checks explicitly requested by each case.
        case_required_failures: List[str] = []
        for check_name in case.get("required_checks", []):
            handler = CHECK_HANDLERS.get(check_name)
            if handler is None:
                case_required_failures.append(f"unknown check: {check_name}")
                continue
            required_counts[check_name]["total"] += 1
            ok, reason = handler(case, response, catalog)
            if ok:
                required_counts[check_name]["passed"] += 1
            else:
                case_required_failures.append(f"{check_name}: {reason}")
        if case_required_failures:
            required_failures.append((case_id, "; ".join(case_required_failures)))

        # Layer B: Full-suite safety checks applied everywhere they are applicable.
        case_full_failures: List[str] = []
        for metric, (handler, applicable) in FULL_SUITE_CHECKS.items():
            if not applicable(case, response):
                continue
            full_suite_counts[metric]["total"] += 1
            ok, reason = handler(case, response, catalog)
            if ok:
                full_suite_counts[metric]["passed"] += 1
            else:
                case_full_failures.append(f"{metric}: {reason}")
        if case_full_failures:
            full_suite_failures.append((case_id, "; ".join(case_full_failures)))

    req_passed = sum(v["passed"] for v in required_counts.values())
    req_total = sum(v["total"] for v in required_counts.values())
    full_passed = sum(v["passed"] for v in full_suite_counts.values())
    full_total = sum(v["total"] for v in full_suite_counts.values())

    adv_passed, adv_total, adv_failures = run_adversarial_checks(catalog, test_cases)

    print(f"Total test cases: {len(test_cases)}")
    print()
    print("Required-check score (per test-case contract):")
    required_order = [
        "status_correct",
        "language_correct",
        "budget_respected",
        "age_respected",
        "stock_respected",
        "no_hallucinated_product_ids",
        "arabic_output_present",
        "discount_math_correct",
        "asks_clarifying_question",
        "does_not_force_recommendation",
        "category_relevant",
        "semantic_relevance",
    ]
    labels = {
        "status_correct": "Status correct",
        "language_correct": "Language correct",
        "budget_respected": "Budget respected",
        "age_respected": "Age respected",
        "stock_respected": "Stock respected",
        "no_hallucinated_product_ids": "No hallucinated product IDs",
        "arabic_output_present": "Arabic output present",
        "discount_math_correct": "Discount math correct",
        "asks_clarifying_question": "Asks clarifying question",
        "does_not_force_recommendation": "Does not force recommendation",
        "category_relevant": "Category relevant",
        "semantic_relevance": "Semantic relevance",
    }
    for metric in required_order:
        p = required_counts[metric]["passed"]
        t = required_counts[metric]["total"]
        print(f"{labels[metric]}: {p}/{t}")
    print(f"Required-check overall: {req_passed}/{req_total}")

    print()
    print("Full-suite safety score (applied where applicable):")
    full_order = [
        "no_hallucinated_product_ids",
        "stock_respected",
        "arabic_output_present",
        "discount_math_correct",
        "budget_respected",
        "age_respected",
        "no_recommendations_for_non_success",
    ]
    full_labels = {
        "no_hallucinated_product_ids": "No hallucinated product IDs",
        "stock_respected": "Stock respected",
        "arabic_output_present": "Arabic output present (when recommendations exist)",
        "discount_math_correct": "Discount math correct (when add-on exists)",
        "budget_respected": "Budget respected (when budget exists)",
        "age_respected": "Age respected (when age exists)",
        "no_recommendations_for_non_success": "No forced recommendations for non-success statuses",
    }
    for metric in full_order:
        p = full_suite_counts[metric]["passed"]
        t = full_suite_counts[metric]["total"]
        print(f"{full_labels[metric]}: {p}/{t}")
    print(f"Full-suite overall: {full_passed}/{full_total}")

    print()
    if required_failures:
        print("Required-check failures:")
        for case_id, reason in required_failures:
            print(f"- {case_id}: {reason}")
    else:
        print("Required-check failures: none")

    print()
    if full_suite_failures:
        print("Full-suite safety failures:")
        for case_id, reason in full_suite_failures:
            print(f"- {case_id}: {reason}")
    else:
        print("Full-suite safety failures: none")

    print()
    print(f"Adversarial checks passed: {adv_passed}/{adv_total}")
    if adv_failures:
        for item in adv_failures:
            print(f"- {item}")

    known_failure_line = "none"
    if required_failures:
        known_failure_line = f"required-check failure in {required_failures[0][0]}"
    elif full_suite_failures:
        known_failure_line = f"full-suite failure in {full_suite_failures[0][0]}"
    elif adv_failures:
        known_failure_line = adv_failures[0]
    print(f"Known failure summary: {known_failure_line}")

    has_failures = bool(required_failures or full_suite_failures or adv_failures or adv_passed != adv_total)
    return 1 if has_failures else 0


if __name__ == "__main__":
    raise SystemExit(run_all_evals())
