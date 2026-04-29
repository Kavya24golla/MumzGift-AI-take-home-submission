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

## Semantic Bundle Matching
Instead of hand-writing every possible product pair, the system embeds product descriptions and assigns broad semantic groups such as `sensory_play`, `pretend_play`, `feeding_support`, and `bath_care`. Add-ons are selected only when semantic compatibility with the main product and user intent crosses a threshold. This avoids irrelevant bundles like sensory toy + bottle brush while still supporting varied user language.

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
- `Thoughtful toy gift for a 6-month-old under 200 AED`
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
    "preferences": ["toys", "thoughtful"],
    "assumptions": [],
    "missing_fields": []
  },
  "recommendations": [
    {
      "main_product": {
        "product_id": "P001",
        "name_en": "Soft Sensory Baby Toy",
        "name_ar": "لعبة حسية ناعمة",
        "category": "toys",
        "price_aed": 89.0,
        "age_min_months": 3,
        "age_max_months": 12,
        "tags": ["gift", "sensory", "soft", "thoughtful"],
        "in_stock": true
      },
      "optional_addon": {
        "product_id": "P014",
        "name_en": "Soft Building Blocks",
        "name_ar": "مكعبات ناعمة",
        "price_aed": 99.0,
        "discount_percent": 10.0,
        "original_total_aed": 188.0,
        "discounted_total_aed": 169.2,
        "savings_aed": 18.8,
        "bundle_relevance": {
          "semantic_group_main": "sensory_play",
          "semantic_group_addon": "sensory_play",
          "semantic_similarity": 0.74,
          "query_alignment": 0.61,
          "final_bundle_score": 0.70,
          "reason": "Both products support sensory play and early-stage gifting intent."
        }
      },
      "reason_en": "At 6 months, babies are actively discovering texture and sound — a soft sensory toy gives them something safe to mouth, squeeze, and explore during this exact developmental window.",
      "reason_ar": "في عمر ٦ أشهر، الطفل يبدأ يكتشف الملمس والأصوات بشكل فعلي — اللعبة الحسية الناعمة تعطيه شيئاً آمناً يستكشفه ويعبّر فيه بيديه الصغيرة.",
      "confidence": 0.9
    }
  ],
  "validation": {
    "budget_respected": true,
    "age_respected": true,
    "all_products_in_stock": true,
    "no_hallucinated_product_ids": true,
    "arabic_output_present": true,
    "discount_math_correct": true,
    "bundle_relevance": true
  }
}
```

## Before / After Bundle Quality
- Query: `i want to gift a 3yrs baby who likes dolls`
  - Before: Doll mains + weak add-ons (`Baby Socks`, `Sippy Cup`, `Snack Cup`) and generic sensory reasons.
  - After: Doll mains + pretend-play relevant add-ons (for example `Mini Doll Blanket`, `Pretend Play Story Book`) with bundle relevance scoring.
- Query: `Gift for a 6-month-old baby under 200 AED`
  - Before: Could return weak utility add-ons due simple category rules.
  - After: Add-ons selected by semantic compatibility and intent alignment, or omitted with `No suitable add-on found for this intent.`
- Query: `Useful feeding gift for a 9-month-old under 150 AED`
  - Before: Category-only matching could drift.
  - After: Feeding products pair with feeding-support add-ons via semantic group + threshold checks.

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

## Loom Demo (3 Minutes)
- Demo the Streamlit UI (`python -m streamlit run app/streamlit_app.py`), not only docs/evals.
- Show 5 inputs: EN success, AR success, feeding success with add-on, impossible budget, and clarification case.
- Point to one uncertainty path and one validation proof in UI badges/raw JSON.

## Tooling Transparency

Models and harnesses used:

- Claude Sonnet (claude.ai): prompt iteration for the query 
  extractor and bilingual response writer. Used for architecture 
  planning and README drafting.

- GPT-4o (ChatGPT): eval case brainstorming, adversarial test 
  input generation, code review suggestions.

- Cursor/KiloCode: code generation and refactoring across 
  response_writer.py, bundle_engine.py, and catalog_search.py. 
  Used in agent loop mode for multi-file edits.

- Python + Pydantic: all deterministic validation. 
  No LLM involved in guardrail logic.

How I used them:
Pair-coding for implementation. One-shot generation for boilerplate. 
Prompt iteration for the Arabic copywriting instructions — took 
4 rounds to eliminate translated-English patterns.

Where I overruled the AI:
The LLM initially suggested letting the model rank and select 
products directly. I overruled this entirely — product selection, 
age checks, budget checks, stock checks, ID validation, discount 
math, and uncertainty routing are all deterministic. The LLM 
only extracts intent and writes bilingual copy.

What did not work:
Early Arabic prompts produced reasons that read like translated 
English. Fixed by adding explicit Gulf Arabic dialect instructions 
and banning specific templated phrases in the system prompt.

## Why This Problem / Tradeoffs

Why I picked this problem:
Gift intent sits directly at the purchase decision layer. 
A good recommendation does not just answer a question — it 
creates a cart. No other example on the brief connects user 
intent to direct revenue as immediately as this one. 
Mumzworld serves high-intent gifting moments (baby showers, 
visits, milestones) where a fast, confident recommendation 
drives conversion.

What I rejected:
- Pediatric symptom triage: high-risk medical domain. 
  Wrong outputs have real consequences. 5 hours is not 
  enough to handle safely.
- Operations dashboard: internally useful but weak 
  customer-facing impact. Needs realistic order data 
  I do not have.
- Review synthesizer: useful but internal-only. 
  No direct purchase connection.
- Product image to PDP: interesting multimodal problem 
  but output quality is hard to eval rigorously in 5 hours.

Architecture choice:
LLM handles only two things — messy intent extraction and 
short bilingual copy. Everything else is deterministic. 
This keeps the system auditable, testable, and safe from 
hallucination at the product and price layer.

What I cut:
- Live Mumzworld catalog integration
- Dynamic pricing and real-time stock
- User history and personalisation
- Fine-tuning for Arabic dialect variants
- Payment or cart API integration

What I would build next:
- Real catalog API integration
- Per-country GCC preference tuning (KSA vs UAE vs Kuwait)
- A/B testing bundle offer conversion
- Human review dashboard for failed or low-confidence queries
- Stronger Arabic dialect coverage beyond Gulf MSA

## Known Limitations
- Synthetic catalog only (no live retail integration).
- Rule-first parsing can miss some edge phrasing.
- Arabic copy is written fresh per product, not translated from 
  English. Feminine/masculine gender agreement and Gulf dialect 
  phrasing are enforced at the prompt level. Deep dialect 
  personalisation per GCC country (KSA vs UAE vs Kuwait) 
  remains a future improvement.
- Ranking is intentionally simple and explainable.

## What I Would Build Next
- Wider Arabic dialect robustness and stronger paraphrase coverage.
- Richer intent tests and error taxonomy.
- Explainable score breakdown in the UI.
- Scalable indexed retrieval for larger catalogs.
