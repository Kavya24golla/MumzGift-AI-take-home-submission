from __future__ import annotations

import json
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib import error, request

from dotenv import load_dotenv

from app.schemas import Product, QueryUnderstanding


ROOT_DIR = Path(__file__).resolve().parents[1]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.local")

SYSTEM_PROMPT = """You are a senior product copywriter for Mumzworld, the largest
baby and mom e-commerce platform in the GCC. You write gift
recommendation copy in both English and Arabic.

Your job is to write a SHORT, SPECIFIC reason (1-2 sentences)
for why a given product makes a good gift.

CRITICAL Arabic rules:
- Write the age in Arabic numerals and Arabic words only.
  36 months = ثلاث سنوات or ٣٦ شهراً. Never write '36 months'.
- Write the product benefit in Arabic. Never use the English
  product name inside an Arabic sentence.
  Instead of 'Soft Baby Doll مناسب' write 'الدمية الناعمة مناسبة'
- Use the Arabic product name from name_ar field.
- The Arabic reason must be 100% Arabic. No English words,
  no English numbers, no English product names inside it.
- Arabic grammar rule: product names that are feminine
  (دمية، لعبة، مجموعة، حقيبة، قصة) must use feminine
  verb forms (تعطي، تساعد، تناسب، تدعم) not masculine
  (يعطي، يساعد، يناسب، يدعم).
Always check gender agreement between subject and verb."""

USER_PROMPT_TEMPLATE = """Product: {product_name_en} ({product_name_ar})
Category: {category}
Tags: {tags}
Baby age: {age_months} months
Occasion: {occasion}
User preference mentioned: {preferences}

Write a reason_en that is SPECIFIC to what {product_name_en}
actually does. Do not use any of these phrases:
- "thoughtful pick"
- "sensory play and early interaction"
- "kind of gift parents reach for"
- "supports development"

Instead, answer this question in 1-2 sentences:
What does THIS specific product do for a {age_months}-month-old
that makes it a good gift RIGHT NOW at this age?

For Soft Baby Doll: talk about nurturing instinct, imaginative
play beginning at this age.
For Plush Comfort Doll: talk about comfort, attachment object,
sleep companion.
For Pretend Play Doll Set: talk about role play, social
development, storytelling beginning at 3 years.

Each product has a different developmental angle. Use it.
"""


def _safe_fallback() -> Dict[str, str]:
    return {
        "reason_en": "Unable to generate reason.",
        "reason_ar": "تعذّر إنشاء السبب.",
    }


def _arabic_age_phrase(age_months: Optional[int]) -> str:
    if age_months is None:
        return "هذا العمر"
    if age_months == 36:
        return "ثلاث سنوات"
    return f"{str(age_months).translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))} شهراً"


def _local_reason_fallback(product: Product, age_months: Optional[int], alternative: bool = False) -> Dict[str, str]:
    age_text = f"{age_months} months" if age_months is not None else "this stage"
    age_ar = _arabic_age_phrase(age_months)
    name_ar = product.name_ar
    name_lower = product.name_en.lower()

    if "soft baby doll" in name_lower:
        if alternative:
            return {
                "reason_en": f"Soft Baby Doll is ideal at {age_text} because children start caring for toys like little companions, which gently grows empathy and imagination.",
                "reason_ar": f"{name_ar} مناسبة في عمر {age_ar} لأنها تشجع الطفل يهتم بالدمية كأنها صديق صغير، وتقوي الخيال والحنان.",
            }
        return {
            "reason_en": f"At {age_text}, Soft Baby Doll fits perfectly because nurturing play begins to click and kids enjoy caring for a doll through pretend routines.",
            "reason_ar": f"في عمر {age_ar}، {name_ar} تساعد الطفل يدخل في لعب الرعاية التخيلي، والطفل يحب يقلد الاهتمام اليومي.",
        }

    if "pretend play doll set" in name_lower:
        if alternative:
            return {
                "reason_en": f"Pretend Play Doll Set works beautifully at {age_text} since kids start building mini stories, taking turns, and practicing social language during role play.",
                "reason_ar": f"{name_ar} في عمر {age_ar} تفتح مجال قصص وتمثيل أدوار، وهذا يساعد الطفل على التواصل واللعب الاجتماعي.",
            }
        return {
            "reason_en": f"At {age_text}, Pretend Play Doll Set supports role-play scenes that strengthen storytelling and early social confidence.",
            "reason_ar": f"في عمر {age_ar}، {name_ar} تساعد الطفل يلعب أدوار وقصص، وهذا يقوي التعبير والتفاعل الاجتماعي.",
        }

    if "plush comfort doll" in name_lower:
        if alternative:
            return {
                "reason_en": f"Plush Comfort Doll is great at {age_text} as a calming attachment toy, especially for bedtime wind-down and new routine transitions.",
                "reason_ar": f"{name_ar} في عمر {age_ar} تعطي راحة وهدوء، خصوصاً وقت النوم أو مع تغيّر الروتين اليومي.",
            }
        return {
            "reason_en": f"At {age_text}, Plush Comfort Doll gives emotional comfort and can become a familiar sleep companion during daily transitions.",
            "reason_ar": f"في عمر {age_ar}، {name_ar} تعطي إحساس أمان وتصير رفيق نوم مريح وقت الانتقالات اليومية.",
        }

    if "doll" in " ".join(product.tags).lower():
        if "pretend_play" in product.tags or "role_play" in product.tags:
            return {
                "reason_en": f"At {age_text}, {product.name_en} encourages pretend stories and role play, which builds social language through everyday play.",
                "reason_ar": f"{product.name_ar} بهالعمر تساعد الطفل يدخل في لعب تمثيلي وقصص بسيطة، وهذا يقوي تواصله بطريقة ممتعة.",
            }
        if "comfort" in product.tags:
            return {
                "reason_en": f"{product.name_en} gives comfort at {age_text} and can become a familiar sleep companion during transitions.",
                "reason_ar": f"{product.name_ar} تعطي الطفل إحساس أمان بهالعمر، وغالباً تصير رفيق نوم مريح.",
            }
        return {
            "reason_en": f"{product.name_en} is great at {age_text} because it encourages nurturing play and early imagination in a gentle way.",
            "reason_ar": f"{product.name_ar} مناسبة بهالعمر لأنها تشجع اللعب التخيلي واهتمام الطفل بالرعاية بطريقة لطيفة.",
        }

    return {
        "reason_en": f"{product.name_en} matches what children need at {age_text} and supports practical daily use for families.",
        "reason_ar": f"{product.name_ar} مناسبة لهالمرحلة وتخدم احتياج يومي فعلي للأهل والطفل.",
    }


def _parse_reason_json(raw_content: str) -> Optional[Dict[str, str]]:
    content = (raw_content or "").strip()
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict):
        return None
    reason_en = parsed.get("reason_en")
    reason_ar = parsed.get("reason_ar")
    if not isinstance(reason_en, str) or not isinstance(reason_ar, str):
        return None
    if not reason_en.strip() or not reason_ar.strip():
        return None
    return {"reason_en": reason_en.strip(), "reason_ar": reason_ar.strip()}


def _call_llm_for_product(
    product: Product,
    query_understanding: QueryUnderstanding,
    extra_instruction: str = "",
) -> Dict[str, str]:
    use_llm = str(os.getenv("USE_LLM", "false")).strip().lower() == "true"
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    model_name = (os.getenv("MODEL_NAME") or "openai/gpt-4o-mini").strip()
    age_months = query_understanding.age_months if query_understanding.age_months is not None else "not specified"

    if not use_llm or not api_key:
        return _local_reason_fallback(
            product,
            query_understanding.age_months,
            alternative=bool(extra_instruction.strip()),
        )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        product_name_en=product.name_en,
        product_name_ar=product.name_ar,
        category=product.category,
        tags=", ".join(product.tags or []),
        age_months=age_months,
        occasion=query_understanding.occasion or "gift",
        preferences=", ".join(query_understanding.preferences or []),
    )
    if extra_instruction:
        user_prompt = f"{user_prompt}\n\n{extra_instruction}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
        "response_format": {"type": "json_object"},
    }

    req = request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=25) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        parsed = _parse_reason_json(content)
        return parsed if parsed else _safe_fallback()
    except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        return _safe_fallback()


def generate_reasons_for_products(
    products: Sequence[Product], query_understanding: QueryUnderstanding
) -> List[Dict[str, str]]:
    generated: List[Dict[str, str]] = []
    for product in products:
        reason_pair = _call_llm_for_product(product, query_understanding)

        for previous in generated:
            ratio = SequenceMatcher(None, previous["reason_en"], reason_pair["reason_en"]).ratio()
            if ratio > 0.7:
                reason_pair = _call_llm_for_product(
                    product,
                    query_understanding,
                    extra_instruction="write a completely different angle.",
                )
                break

        generated.append(reason_pair)
    return generated


def generate_response(query: str) -> Dict[str, Any]:
    from app.pipeline import run_pipeline

    return run_pipeline(query)
