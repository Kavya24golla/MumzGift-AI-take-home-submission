from __future__ import annotations

import re
from typing import List, Optional

from app.schemas import QueryUnderstanding


ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
ARABIC_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _normalize_text(text: str) -> str:
    normalized = text.strip()
    normalized = normalized.translate(ARABIC_DIGIT_MAP)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def detect_language(query: str) -> str:
    return "ar" if ARABIC_CHAR_RE.search(query) else "en"


def extract_age_months(query: str, language: str) -> Optional[int]:
    q = _normalize_text(query.lower())

    if "newborn" in q or "حديث الولادة" in q or "مولود" in q:
        return 0

    if language == "en":
        month_match = re.search(r"(\d+)\s*[- ]?(?:month|months|mo)\b", q)
        if not month_match:
            month_match = re.search(r"(\d+)\s*[- ]?month[- ]?old\b", q)
        if month_match:
            return int(month_match.group(1))

        year_compact_match = re.search(r"(\d+)\s*(?:yrs|yr|years|year|yo|y\/o)\b", q)
        if not year_compact_match:
            year_compact_match = re.search(r"(\d+)\s*[- ]?year[- ]?old\b", q)
        if year_compact_match:
            return int(year_compact_match.group(1)) * 12
    else:
        month_match = re.search(r"(\d+)\s*(?:شهر|أشهر|شهور)\b", q)
        if month_match:
            return int(month_match.group(1))

        year_match = re.search(r"(\d+)\s*(?:سنة|سنوات|عام|أعوام)\b", q)
        if year_match:
            return int(year_match.group(1)) * 12

    return None


def extract_budget_aed(query: str, language: str) -> Optional[float]:
    q = _normalize_text(query.lower())

    en_patterns = [
        r"(?:under|below|less than)\s*(\d+(?:\.\d+)?)\s*(?:aed|dhs|dirham|dirhams)?",
        r"(?:budget|within)\s*(?:of)?\s*(\d+(?:\.\d+)?)\s*(?:aed|dhs|dirham|dirhams)?",
        r"(\d+(?:\.\d+)?)\s*(?:aed|dhs|dirham|dirhams)\b",
    ]
    ar_patterns = [
        r"(?:بحدود|تحت|اقل من|أقل من)\s*(\d+(?:\.\d+)?)\s*(?:درهم)?",
        r"(?:ميزانية|الميزانية)\s*(?:\S+\s*)?(\d+(?:\.\d+)?)\s*(?:درهم)?",
        r"(\d+(?:\.\d+)?)\s*درهم",
    ]

    patterns = ar_patterns if language == "ar" else en_patterns
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return float(match.group(1))
    return None


def extract_recipient(query: str, language: str) -> Optional[str]:
    q = _normalize_text(query.lower())

    if any(word in q for word in ["husband", "wife", "boyfriend", "girlfriend"]):
        return "adult"

    if any(word in q for word in ["زوج", "زوجي", "زوجتي"]):
        return "adult"
    if any(word in q for word in ["مولود", "حديث الولادة", "رضيع"]):
        return "newborn_baby"
    if any(word in q for word in ["طفل", "طفلة"]):
        return "child"

    if "newborn" in q:
        return "newborn_baby"
    if "infant" in q:
        return "infant"
    if "toddler" in q:
        return "toddler"
    if any(word in q for word in ["child", "kid"]):
        return "child"
    if "baby" in q:
        return "newborn_baby"
    return None


def extract_occasion(query: str, language: str) -> str:
    q = _normalize_text(query.lower())
    if language == "ar":
        return "gift" if "هدية" in q else "shopping"
    return "gift" if "gift" in q else "shopping"


def extract_preferences(query: str, language: str) -> List[str]:
    q = _normalize_text(query.lower())
    preferences: List[str] = []

    # Extract preferences from explicit interest language.
    # Examples:
    # - likes dolls -> dolls, soft_toy
    # - loves music -> music, educational
    # - into cars -> vehicles, toy_cars
    # - organic stuff -> organic, natural
    interest_patterns = [
        r"(?:likes?|loves?|into)\s+([a-z_ ]+?)(?:$|[,.!?]| and | for | who )",
        r"(?:تحب|يحب|يعشق)\s+([^\s,.!?]+)",
    ]
    mentions: List[str] = []
    for pattern in interest_patterns:
        for match in re.finditer(pattern, q):
            value = match.group(1).strip()
            if value:
                mentions.append(value)

    related_interest_map = {
        "doll": ["dolls", "soft_toy"],
        "dolls": ["dolls", "soft_toy"],
        "دمى": ["dolls", "soft_toy"],
        "الدمى": ["dolls", "soft_toy"],
        "music": ["music", "educational"],
        "cars": ["vehicles", "toy_cars"],
        "organic": ["organic", "natural"],
    }
    for mention in mentions:
        for key, tags in related_interest_map.items():
            if key in mention:
                preferences.extend(tags)

    keyword_map = {
        "feeding": ["feeding", "weaning", "bottle", "spoon", "إطعام", "رضاعة", "ملعقة", "فطام"],
        "bath": ["bath", "shower", "حمام", "استحمام"],
        "diapers": ["diaper", "wipes", "حفاض", "مناديل"],
        "clothing": ["clothing", "romper", "socks", "ملابس", "جوارب", "رومبر"],
        "toys": ["toy", "play", "pretend play", "role play", "لعبة", "ألعاب", "اللعب التخيلي"],
        "organic": ["organic", "عضوي"],
        "wooden": ["wooden", "خشب"],
        "educational": ["educational", "learning", "تعليمي", "تعلم"],
        "soft": ["soft", "ناعم"],
        "colorful": ["colorful", "colourful", "ملون"],
        "pretend_play": ["pretend play", "role play", "play kitchen", "dress up", "اللعب التخيلي", "تمثيل"],
        "dolls": ["doll", "dolls", "dollhouse", "دمى", "الدمى"],
        "soft_toy": ["soft toy", "plush", "stuffed", "دمية ناعمة"],
        "thoughtful": ["thoughtful", "special", "مميز"],
        "useful": ["useful", "practical", "مفيد", "عملي"],
    }
    for label, keywords in keyword_map.items():
        if any(keyword in q for keyword in keywords):
            preferences.append(label)

    filtered = [pref for pref in preferences if pref not in {"gift", "هدية"}]
    return list(dict.fromkeys(filtered))


def extract_query_understanding(query: str) -> QueryUnderstanding:
    language = detect_language(query)
    age_months = extract_age_months(query, language)
    recipient = extract_recipient(query, language)
    budget_aed = extract_budget_aed(query, language)
    occasion = extract_occasion(query, language)
    preferences = extract_preferences(query, language)

    if age_months is not None:
        if age_months <= 3:
            recipient = "newborn"
        elif 4 <= age_months <= 12:
            recipient = "infant"
        elif 13 <= age_months <= 36:
            recipient = "toddler"
        else:
            recipient = "child"

    assumptions: List[str] = []
    if budget_aed is None:
        budget_aed = 200.0
        assumptions.append("No budget mentioned. Defaulting to 200 AED — a common gift range in the GCC.")

    missing_fields: List[str] = []
    if age_months is None:
        missing_fields.append("age_months")
    if recipient is None:
        missing_fields.append("recipient")

    return QueryUnderstanding(
        language=language,
        recipient=recipient,
        age_months=age_months,
        budget_aed=budget_aed,
        occasion=occasion,
        preferences=preferences,
        assumptions=assumptions,
        missing_fields=missing_fields,
    )
