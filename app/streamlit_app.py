from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from app.offer_engine import build_offer_for_main
from app.pipeline import run_pipeline
from app.schemas import Product


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "products.json"


EXAMPLE_QUERIES = [
    "Gift for a 6-month-old baby under 200 AED",
    "أريد هدية لطفل عمره ٦ أشهر بحدود ٢٠٠ درهم",
    "Useful feeding gift for a 9-month-old under 150 AED",
    "Gift for newborn under 5 AED",
    "Something nice for a baby",
]


def _render_query_understanding(response: Dict[str, Any]) -> None:
    st.subheader("Query Understanding")
    understanding = response.get("query_understanding")
    if understanding:
        st.json(understanding)
    else:
        st.info("No query understanding available.")


def _confidence_label(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "Unknown confidence"
    if 0.8 <= score <= 1.0:
        return "High confidence"
    if 0.5 <= score < 0.8:
        return "Moderate — assumptions made"
    return "Low — clarification recommended"


def _render_recommendations(response: Dict[str, Any]) -> None:
    st.subheader("Recommendations")
    recommendations: List[Dict[str, Any]] = response.get("recommendations", []) or []
    if not recommendations:
        st.info("No recommendations returned for this request.")
        return

    budget_aed = float((response.get("query_understanding") or {}).get("budget_aed") or 0)
    with DATA_PATH.open("r", encoding="utf-8") as f:
        catalog_raw = json.load(f)
    catalog_products = [Product(**item) for item in catalog_raw]

    for idx, rec in enumerate(recommendations, start=1):
        main = rec.get("main_product", {})
        addon = rec.get("optional_addon")
        with st.container(border=True):
            st.markdown(f"**#{idx} {main.get('name_en', 'Unknown Product')}**")
            st.caption(main.get("name_ar", ""))
            c1, c2, c3 = st.columns(3)
            c1.write(f"Product ID: `{main.get('product_id', '-')}`")
            c2.write(f"Category: `{main.get('category', '-')}`")
            c3.write(f"Price: **{main.get('price_aed', '-')} AED**")

            st.write(f"Reason (EN): {rec.get('reason_en', '')}")
            st.write(f"Reason (AR): {rec.get('reason_ar', '')}")
            confidence = rec.get("confidence", "-")
            st.write(f"Confidence: `{confidence}` — {_confidence_label(confidence)}")

            if addon:
                st.markdown("**Optional Smart Offer**")
                st.write(
                    f"{addon.get('name_en', '')} ({addon.get('name_ar', '')}) - "
                    f"`{addon.get('price_aed', '-')}` AED"
                )
                st.write(
                    f"Discount: `{addon.get('discount_percent', '-')}`% | "
                    f"Original total: `{addon.get('original_total_aed', '-')}` AED | "
                    f"Discounted total: `{addon.get('discounted_total_aed', '-')}` AED | "
                    f"Savings: `{addon.get('savings_aed', '-')}` AED"
                )
                bundle_relevance = addon.get("bundle_relevance", {}) or {}
                if bundle_relevance:
                    bundle_reason = str(bundle_relevance.get("reason", "")).strip()
                    if bundle_reason:
                        bundle_reason = bundle_reason[0].lower() + bundle_reason[1:]
                    st.write(
                        f"Bundle relevance: {bundle_relevance.get('final_bundle_score', '-')} - {bundle_reason}"
                    )
                    st.write(
                        f"Semantic groups: main=`{bundle_relevance.get('semantic_group_main', '-')}`, "
                        f"add-on=`{bundle_relevance.get('semantic_group_addon', '-')}` | "
                        f"semantic=`{bundle_relevance.get('semantic_similarity', '-')}` | "
                        f"query alignment=`{bundle_relevance.get('query_alignment', '-')}`"
                    )
            else:
                try:
                    main_product_model = Product(**main)
                    _addon_candidate, offer_reason = build_offer_for_main(
                        main_product=main_product_model,
                        catalog=catalog_products,
                        query_understanding=response.get("query_understanding", {}),
                        budget_aed=budget_aed,
                    )
                except Exception:
                    offer_reason = "No suitable add-on found for this intent."
                st.caption(offer_reason)


def _render_validation(response: Dict[str, Any]) -> None:
    st.subheader("Validation Badges")
    validation = response.get("validation")
    if not validation:
        st.info("Validation block not applicable for this status.")
        return

    for key, value in validation.items():
        label = key.replace("_", " ").title()
        if value:
            st.success(f"{label}: ✅ PASS")
        else:
            st.error(f"{label}: ❌ FAIL")

    from app.validator import reasons_are_product_specific

    recommendations: List[Dict[str, Any]] = response.get("recommendations", []) or []
    reasons_specific = reasons_are_product_specific(recommendations)
    if reasons_specific:
        st.success("Reasons Are Product-Specific: ✅ PASS")
    else:
        st.error("Reasons Are Product-Specific: ❌ FAIL")


def _render_status_section(response: Dict[str, Any]) -> None:
    status = response.get("status")
    if status == "success":
        st.success("Success: valid recommendations generated.")
    elif status == "needs_clarification":
        st.warning("Needs clarification.")
        st.write(f"Missing fields: {response.get('missing_fields', [])}")
        st.write(f"Question (EN): {response.get('question_en', '')}")
        st.write(f"Question (AR): {response.get('question_ar', '')}")
    elif status in {"no_valid_match", "no_valid_cart"}:
        st.warning("No valid match.")
        st.write(f"Reason (EN): {response.get('reason_en', '')}")
        st.write(f"Reason (AR): {response.get('reason_ar', '')}")
    elif status == "out_of_scope":
        st.info("Out of scope.")
        st.write(f"Reason (EN): {response.get('reason_en', '')}")
        st.write(f"Reason (AR): {response.get('reason_ar', '')}")
    else:
        st.error(f"Unknown status: {status}")


def main() -> None:
    st.set_page_config(page_title="MumzGift AI", page_icon="🎁", layout="wide")
    st.title("MumzGift AI: Bilingual Gift Finder with Guardrailed Smart Offers")
    st.write(
        "MumzGift AI is not a generic chatbot. It combines EN/AR intent understanding with deterministic "
        "product filtering, age/budget/stock guardrails, and validated smart offers."
    )

    st.markdown("**Example Queries**")
    for example in EXAMPLE_QUERIES:
        st.code(example)

    default_query = EXAMPLE_QUERIES[0]
    with st.form("mumzgift_form"):
        query = st.text_input("Enter a gift request (English or Arabic)", value=default_query)
        submitted = st.form_submit_button("Find Gift")

    if not submitted:
        return

    with st.spinner("Running deterministic pipeline..."):
        response = run_pipeline(query)

    _render_status_section(response)
    _render_query_understanding(response)
    _render_recommendations(response)
    _render_validation(response)

    with st.expander("Raw JSON"):
        st.code(json.dumps(response, ensure_ascii=False, indent=2), language="json")


if __name__ == "__main__":
    main()
