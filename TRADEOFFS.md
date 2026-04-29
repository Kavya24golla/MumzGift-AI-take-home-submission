# TRADEOFFS.md

## Why I Picked This Problem
I chose bilingual gift finding because it is directly aligned with Mumzworld’s commerce context and allows measurable guardrails (budget, age, stock, catalog grounding) within a tight take-home scope.

## What I Rejected and Why
- Pediatric triage: higher safety and clinical risk, not suitable for a short intern prototype.
- Operations dashboard: lower direct customer impact for this assignment.
- Support triage: useful but less tied to shopping outcomes and recommendation quality.
- Product image PDP generation: visually interesting, but weaker on core retrieval/guardrail logic.
- Duplicate detector: useful backend utility, but less compelling as an end-user assistant demo.

## Why I Avoided Full RAG
For an 80-item synthetic catalog, deterministic filtering/ranking is faster, clearer, and easier to validate than a full RAG stack. Full RAG would increase complexity without proving more signal in a 5-hour assignment.

## Why I Did Not Let The LLM Choose Products
Free-form LLM selection risks hallucinated products, wrong age fit, and budget misses.  
I restricted selection to deterministic code over known catalog rows for reliability.

## Why Product Selection Is Deterministic
- Enforces stock/budget/age constraints reliably.
- Makes behavior explainable and testable.
- Supports strict eval assertions beyond vibes.

## Why Offers Are Optional and Simple
- One add-on keeps UX clear and safe.
- Fixed 10% discount keeps math auditable.
- Offer only appears if discounted total still respects user budget.

## What I Cut For 5-Hour Scope
- Complex ranking model / learning-to-rank
- Real-time inventory and pricing integrations
- Payments/cart integrations
- Full multilingual NLU model training/fine-tuning
- Personalized user history and experimentation framework

## What I Would Build Next
- More robust EN/AR slot extraction and ambiguity handling.
- Better Arabic generation variety and style controls.
- Retrieval index over larger, messier catalogs.
- A/B testing for ranking and add-on relevance.
- Continuous eval dashboard with regression alerts.

