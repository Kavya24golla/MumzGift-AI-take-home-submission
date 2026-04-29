# EVALS.md

Total checks: 86  
Passed: 86  
Failed: 0

Known limitation (honest):  
Current evals are strong on hard safety constraints, but they do not fully measure subjective gift delight (for example, whether recommendations feel emotionally special to a shopper). A future rubric should add human rating for gift appeal and Arabic naturalness.
Additional honest limitation: the current automated suite does not grade emotional resonance quality of bilingual copy.

## Eval Philosophy
This project measures hard constraints and failure modes, not style-only output quality.

## Test Case Categories
- Normal success cases (English and Arabic)
- Budget guardrails
- Age suitability
- Stock exclusion
- Category relevance
- Uncertainty routing (`needs_clarification`, `no_valid_match`, `out_of_scope`)
- Semantic intent coverage

## Metric Table
- `status_correct`
- `language_correct`
- `budget_respected`
- `age_respected`
- `stock_respected`
- `no_hallucinated_product_ids`
- `arabic_output_present`
- `discount_math_correct`
- `asks_clarifying_question`
- `does_not_force_recommendation`
- `category_relevant`
- `semantic_relevance`

## Example Failure Modes Tested
- Over-budget recommendation
- Wrong age range recommendation
- Out-of-stock recommendation
- Hallucinated product ID
- Missing Arabic output
- Broken discount math
- Forced recommendation in non-success statuses

## Adversarial Checks
`evals/run_evals.py` includes explicit corrupted payload tests:
1. Fake `product_id`
2. Out-of-stock product in recommendation
3. Empty Arabic reason
4. Wrong discount math

Latest run:
- Adversarial checks passed: 4/4

## How To Run Evals
```bash
python evals/run_evals.py
```
