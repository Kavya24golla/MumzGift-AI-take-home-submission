# MumzGift AI: Bilingual Gift Finder with Guardrailed Smart Offers

MumzGift AI is a bilingual (English/Arabic) gift finder prototype for Mumzworld-style shopping journeys in the GCC. It converts messy gift intent into grounded recommendations from a synthetic catalog, then applies deterministic commerce guardrails before returning results.  
MumzGift AI is not a generic gift chatbot. The LLM/rules handle messy EN/AR intent and short bilingual copy, while deterministic tools handle product retrieval, age checks, budget checks, stock checks, offer math, validation, and evals.

## Why This Problem Matters for Mumzworld
Parents usually search by life situation, not SKU names. Queries like "gift for a 6-month-old under 200 AED" or "هدية لطفل عمره ٦ أشهر" need fast, safe, and relevant recommendations. This prototype targets that exact purchase-intent layer.

## What The System Does
- Extracts structured intent from EN/AR user text.
- Retrieves candidates from a messy multilingual synthetic catalog.
- Applies deterministic filters for budget, age suitability, and stock.
- Ranks top recommendations and proposes one optional add-on (10% bundle discount).
- Validates final output using schema and business-rule checks.
- Handles uncertainty explicitly (`needs_clarification`, `no_valid_match`, `out_of_scope`).

## Architecture (Text Diagram)
```text
User Query (EN/AR)
  -> Query Extractor
  -> Semantic Catalog Retrieval (local multilingual embeddings)
  -> Deterministic Filter + Rank
  -> Optional Offer Engine
  -> Schema + Business Validation
  -> Bilingual Response Writer
  -> Streamlit UI + Raw JSON + Eval Runner
```

## Non-Trivial AI Engineering Components
1. Tool-style workflow (extraction -> retrieval -> offer -> validator -> response writer)
2. Retrieval over messy multilingual catalog data (EN/AR names, noisy tags, stock gaps)
3. Structured output with validation (Pydantic + strict business rules)
4. Evals beyond vibes (contract checks + full-suite safety + adversarial payload checks)

## Why Semantic Retrieval Instead of Keyword Matching
Gift language is variable across English and Arabic ("3yrs baby likes dolls", "pretend play", "تحب الدمى"). Keyword-only matching is brittle and misses intent variants. Local multilingual embeddings retrieve semantically similar products first, while deterministic guardrails still enforce age, budget, stock, product ID validity, and discount correctness.

## Setup (Under 5 Minutes)
```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Run app:
```bash
python -m streamlit run app/streamlit_app.py
```

Run evals:
```bash
python evals/run_evals.py
```

## Example Inputs
- `Gift for a 6-month-old baby under 200 AED`
- `أريد هدية لطفل عمره ٦ أشهر بحدود ٢٠٠ درهم`
- `Useful feeding gift for a 9-month-old under 150 AED`
- `Gift for newborn under 5 AED`
- `Something nice for a baby`

## Example Output (Success)
```json
{
  "status": "success",
  "query_understanding": {
    "language": "en",
    "recipient": "infant",
    "age_months": 6,
    "budget_aed": 200.0,
    "occasion": "gift",
    "preferences": []
  },
  "recommendations": [
    {
      "main_product": {
        "product_id": "P027",
        "name_en": "Feeding Gift Hamper Mini",
        "name_ar": "سلة إطعام صغيرة",
        "category": "feeding",
        "price_aed": 145.0,
        "age_min_months": 6,
        "age_max_months": 12,
        "tags": ["feeding", "gift", "thoughtful"],
        "in_stock": true
      },
      "optional_addon": {
        "product_id": "P016",
        "name_en": "Feeding Spoon Set",
        "name_ar": "مجموعة ملاعق إطعام",
        "price_aed": 29.0,
        "discount_percent": 10.0,
        "original_total_aed": 174.0,
        "discounted_total_aed": 156.6,
        "savings_aed": 17.4
      }
    }
  ]
}
```

## Eval Summary
- Test cases: 15
- Required-check overall: 86/86
- Full-suite safety overall: 91/91
- Adversarial checks: 4/4
- Known automated check failures: none

## Uncertainty Handling
- `needs_clarification`: missing key details trigger bilingual follow-up.
- `no_valid_match`: no safe in-stock match under constraints.
- `out_of_scope`: non baby/new-mom gifting requests rejected explicitly.

## Tooling Transparency
- ChatGPT/Codex used for architecture support, code drafting support, eval brainstorming, and documentation drafting.
- Python + Pydantic enforce deterministic validation and guardrails.
- LLM/rules are limited to intent parsing and short bilingual copy.
- Human overruled AI for product selection, stock checks, age checks, budget checks, ID validation, discount math, and uncertainty rules.

## Known Limitations
- Synthetic catalog only (no live retail integration).
- Rule-first parsing can miss some edge phrasing.
- Arabic copy is concise and safe but not deeply personalized.
- Ranking is intentionally simple and explainable.

## What I Would Build Next
- Wider Arabic dialect robustness and stronger paraphrase coverage.
- Richer intent tests and error taxonomy.
- Explainable score breakdown in the UI.
- Scalable indexed retrieval for larger catalogs.
