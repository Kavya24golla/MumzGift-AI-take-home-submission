from __future__ import annotations

from typing import Callable, List

from app.schemas import Product


# Ranking helper for deterministic catalog search.
# Priority:
# 1) Sweet spot products: 40%-90% of budget
# 2) >90% of budget
# 3) <40% of budget
def rank_products(
    products: List[Product], budget_aed: float, score_fn: Callable[[Product], float]
) -> List[Product]:
    sweet_low = budget_aed * 0.4
    sweet_high = budget_aed * 0.9

    def tier(product: Product) -> int:
        if sweet_low <= product.price_aed <= sweet_high:
            return 0
        if product.price_aed > sweet_high:
            return 1
        return 2

    return sorted(
        products,
        key=lambda product: (tier(product), -score_fn(product), -product.price_aed),
    )
