from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Dict, List

from app.schemas import Product

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # noqa: BLE001
    SentenceTransformer = None  # type: ignore[assignment]

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # noqa: BLE001
    np = None  # type: ignore[assignment]
    TfidfVectorizer = None  # type: ignore[assignment]
    cosine_similarity = None  # type: ignore[assignment]


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def product_to_search_text(product: Product) -> str:
    tags = ", ".join(product.tags or [])
    use_case = "gift, baby care, family shopping, toddler needs"
    age_text = f"{product.age_min_months} to {product.age_max_months} months"
    return (
        f"name_en: {product.name_en}; "
        f"name_ar: {product.name_ar}; "
        f"category: {product.category}; "
        f"tags: {tags}; "
        f"age_range: {age_text}; "
        f"use_case: {use_case}"
    )


class SemanticProductSearch:
    def __init__(self, products: List[Product]) -> None:
        self.products = products
        self.search_texts = [product_to_search_text(product) for product in products]
        self.use_sentence_transformer = SentenceTransformer is not None
        self.use_tfidf = TfidfVectorizer is not None and cosine_similarity is not None

        if self.use_sentence_transformer:
            self.model = SentenceTransformer(MODEL_NAME)
            self.product_embeddings = self.model.encode(
                self.search_texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        elif self.use_tfidf:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
            self.product_embeddings = self.vectorizer.fit_transform(self.search_texts)
        else:
            self.tokenized = [self._tokenize(text) for text in self.search_texts]

    @staticmethod
    def _tokenize(text: str) -> Counter[str]:
        tokens = [token.strip().lower() for token in text.replace(";", " ").replace(",", " ").split() if token.strip()]
        return Counter(tokens)

    @staticmethod
    def _cosine_counter(a: Counter[str], b: Counter[str]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(a[token] * b.get(token, 0) for token in a.keys())
        norm_a = sqrt(sum(value * value for value in a.values()))
        norm_b = sqrt(sum(value * value for value in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def search(self, query: str, top_k: int = 20) -> List[Dict[str, object]]:
        if self.use_sentence_transformer:
            query_embedding = self.model.encode(
                [query],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            scores = cosine_similarity(query_embedding, self.product_embeddings)[0]
        elif self.use_tfidf:
            query_embedding = self.vectorizer.transform([query])
            scores = cosine_similarity(query_embedding, self.product_embeddings)[0]
        else:
            query_tokens = self._tokenize(query)
            scores = [self._cosine_counter(query_tokens, product_tokens) for product_tokens in self.tokenized]

        top_k = max(1, min(top_k, len(self.products)))
        if np is not None:
            top_indices = np.argsort(scores)[::-1][:top_k]
        else:
            top_indices = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)[:top_k]

        results: List[Dict[str, object]] = []
        for idx in top_indices:
            results.append(
                {
                    "product": self.products[int(idx)],
                    "semantic_score": float(scores[int(idx)]),
                    "search_text": self.search_texts[int(idx)],
                }
            )
        return results
