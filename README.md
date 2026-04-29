# MumzGift AI: Bilingual Gift Finder with Guardrailed Smart Offers

**Walkthrough Video (Google Drive):** [3-minute demo](https://drive.google.com/file/d/1LRClD0P4i-5PthDf-dQwj7AX7VFl6FMi/view?usp=sharing)

## 1) What This Is

MumzGift AI is a bilingual (English/Arabic) gift-finding prototype for a Mumzworld-style GCC shopping flow.  
It turns messy intent like “thoughtful toy gift for a 6-month-old under 200 AED” into grounded catalog recommendations, then enforces deterministic commerce guardrails before returning results.

This is **not** a generic chatbot.  
LLM/rules handle intent parsing + short EN/AR copy. Deterministic code handles retrieval, filtering, ranking, bundle math, validation, and uncertainty routing.

---

## 2) Problem Statement

Parents usually shop by situation, not SKU:
- “Gift for a 6-month-old under 200 AED”
- “I want to gift a 3-year-old who likes dolls”
- “أريد هدية لطفل عمره ٦ أشهر”

A naive LLM assistant can hallucinate products, ignore age/budget/stock, and output weak bundles.  
MumzGift AI solves this with **semantic retrieval + deterministic guardrails + explicit evals**.

---

## 3) Why This Matters for Mumzworld

A good gifting assistant can directly improve:
- Product discovery
- Conversion in high-intent gifting moments
- Basket size with relevant add-ons
- User trust through safe/grounded recommendations
- Arabic shopping quality (native EN/AR response flow)

---

## 4) System Flow

```text
User Query (EN/AR)
  -> Query Extractor
  -> Semantic Catalog Retrieval (local multilingual embeddings)
  -> Deterministic Filter + Rank (budget, age, stock, ID validity)
  -> Semantic Bundle Matcher
  -> Offer Engine (fixed 10% discount)
  -> Schema + Business Validator
  -> Bilingual Response Writer
  -> Streamlit UI + Raw JSON + Eval Runner
```

---

## 5) Non-Trivial AI Engineering Components

1. Tool-style modular workflow (not one prompt).
2. Retrieval over messy multilingual catalog data.
3. Structured output validation (Pydantic + business rules).
4. Evals beyond vibes (contract checks + full-suite safety + adversarial checks).

---

## 6) Why Semantic Retrieval (Not Keyword Matching)

Gift language is highly variable:
- “3yrs baby who likes dolls”
- “toddler who enjoys pretend play”
- “هدية لطفلة تحب الدمى”

Keyword matching is brittle.  
We use local multilingual embeddings for candidate retrieval, then deterministic logic decides what is allowed.

---

## 7) Semantic Bundle Matching (Why It’s Better)

Instead of hard-coding endless pair rules, bundles are selected by:
- Product semantic text embeddings
- Semantic group alignment
- Query alignment
- Deterministic constraints (age/budget/stock/ID/math)

If no relevant add-on passes threshold, the system returns:  
`No suitable add-on found for this intent.`

---

## 8) Setup (Under 5 Minutes)

```bash
git clone https://github.com/Kavya24golla/MumzGift-AI-take-home-submission.git
cd MumzGift-AI-take-home-submission

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

Install + run:
```bash
pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py
python evals/run_evals.py
```

---

## 9) Example Inputs

- `Thoughtful toy gift for a 6-month-old under 200 AED`
- `أريد هدية لطفل عمره ٦ أشهر بحدود ٢٠٠ درهم`
- `Useful feeding gift for a 9-month-old under 150 AED`
- `Gift for newborn under 5 AED`
- `Something nice for a baby`
- `i want to gift a 3yrs baby who likes dolls`

---

## 10) Example Output (Shortened)

```json
{
  "status": "success",
  "query_understanding": {
    "language": "en",
    "recipient": "infant",
    "age_months": 6,
    "budget_aed": 200.0,
    "occasion": "gift",
    "preferences": ["toys", "thoughtful"]
  },
  "recommendations": [
    {
      "main_product": {
        "product_id": "P001",
        "name_en": "Soft Sensory Baby Toy",
        "name_ar": "لعبة حسية ناعمة",
        "category": "toys",
        "price_aed": 89.0
      },
      "optional_addon": {
        "product_id": "P014",
        "discount_percent": 10.0,
        "discounted_total_aed": 169.2,
        "bundle_relevance": {
          "semantic_group_main": "sensory_play",
          "semantic_group_addon": "sensory_play",
          "final_bundle_score": 0.70
        }
      },
      "reason_en": "At 6 months, babies are actively discovering texture and sound, and this soft sensory toy gives safe hands-on exploration right now.",
      "reason_ar": "في عمر ٦ أشهر، الطفل يبدأ يكتشف الملمس والأصوات بشكل فعلي، واللعبة الحسية الناعمة تعطيه تجربة آمنة وممتعة.",
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

---

## 11) Evaluation Summary

Latest run:
- Test cases: **17**
- Required-check score: **106/106**
- Full-suite safety score: **123/123**
- Adversarial checks: **4/4**

Coverage includes:
- Over-budget prevention
- Age mismatch prevention
- Out-of-stock exclusion
- Hallucinated ID detection
- Arabic output presence
- Discount math correctness
- Semantic bundle relevance
- Uncertainty routing correctness

**Honest limitation:** automated evals verify safety and grounding well, but they do not fully score subjective “gift delight” or nuanced Arabic style quality.

---

## 12) Uncertainty Handling

Supported statuses:
- `success`
- `needs_clarification`
- `no_valid_match`
- `out_of_scope`

Examples:
- `Something nice for a baby` -> asks clarification (missing age/budget).
- `Gift for newborn under 5 AED` -> `no_valid_match` (no safe fit).
- `Gift for my husband under 200 AED` -> `out_of_scope`.

---

## 13) Tradeoffs

Chosen because it is close to purchase intent and conversion.

Rejected:
- Pediatric triage (too risky for 5-hour scope)
- Ops dashboard (weaker customer-facing impact)
- Review synthesizer (less direct to cart creation)
- Product image -> PDP (hard to evaluate rigorously in scope)
- Duplicate detector (strong technically, weaker shopper impact)

Design tradeoff:
- LLM/rules only for intent + bilingual copy
- Deterministic logic for product and commerce decisions

---

## 14) Tooling Transparency

Used:
- Claude Sonnet + ChatGPT for architecture iteration, prompt iteration, eval brainstorming, and review suggestions
- Cursor/KiloCode for assisted refactors and code drafting
- Python + Pydantic for deterministic validation and guardrails

Where AI was overruled:
- Product selection remains deterministic
- Age/budget/stock checks deterministic
- ID validation deterministic
- Discount math deterministic
- Uncertainty routing deterministic

---

## 15) What I’d Build Next

- Live catalog API integration
- Country-aware GCC personalization (KSA/UAE/Kuwait)
- A/B tests for bundle conversion lift
- Human review queue for low-confidence/failed cases
- Stronger Arabic dialect coverage at scale

---

## 16) Time Log (~5 Hours)

- Problem framing + scope: ~45 min
- Synthetic catalog + eval design: ~60 min
- Core retrieval/filter/rank/validation pipeline: ~90 min
- Streamlit + bundle logic: ~75 min
- Evals/docs/demo prep: ~60 min

---

MumzGift AI is built as a **testable AI system**, not a prompt demo: semantic understanding where it helps, deterministic guardrails where trust and correctness matter.
