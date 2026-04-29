from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Any, Dict, List, Optional

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
_MODEL: Optional[Any] = None


def _get_model() -> Optional[Any]:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if SentenceTransformer is None:
        return None
    _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def _product_use_case(product: Product) -> str:
    tags = {str(tag).strip().lower() for tag in (product.tags or [])}
    name = product.name_en.lower()
    if {"doll", "dolls", "pretend_play", "role_play"}.intersection(tags):
        return "gift for child who likes dolls, role play, nurturing play, storytelling"
    if "feeding" in tags or product.category == "feeding":
        if "brush" in name or "clean" in tags:
            return "cleaning baby bottles and feeding accessories"
        return "feeding support during weaning, spoons, bowls, bibs, and bottle routines"
    if product.category == "bath":
        return "baby bath comfort, gentle cleaning, and bath-time routines"
    if product.category == "diapers":
        return "daily diapering care and hygiene essentials"
    if product.category == "clothing":
        return "everyday baby comfort, easy wear, and practical gifting"
    if product.category == "new_mom_care":
        return "supporting new mother wellness and early baby-care routines"
    return "baby gifting and family shopping use case"


def _gift_purpose(product: Product) -> str:
    tags = {str(tag).strip().lower() for tag in (product.tags or [])}
    if "gift" in tags:
        return "gift purpose: celebration gifting, milestone present"
    return "gift purpose: practical supportive add-on"


def product_to_semantic_text(product: Product) -> str:
    tags = ", ".join(product.tags or [])
    age_text = f"{product.age_min_months} to {product.age_max_months} months"
    use_case = _product_use_case(product)
    gift_purpose = _gift_purpose(product)
    return (
        f"{product.name_en}. {product.name_ar}. "
        f"Category: {product.category}. "
        f"Tags: {tags}. "
        f"Age range: {age_text}. "
        f"Use case: {use_case}. "
        f"{gift_purpose}."
    )


def _tokenize(text: str) -> Counter[str]:
    tokens = [token.strip().lower() for token in text.replace(";", " ").replace(",", " ").split() if token.strip()]
    return Counter(tokens)


def _cosine_counter(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[token] * b.get(token, 0) for token in a.keys())
    norm_a = sqrt(sum(value * value for value in a.values()))
    norm_b = sqrt(sum(value * value for value in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def build_product_embeddings(products: List[Product]) -> Dict[str, Any]:
    texts = [product_to_semantic_text(product) for product in products]
    model = _get_model()
    if model is not None and cosine_similarity is not None:
        embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        return {"backend": "sentence_transformer", "texts": texts, "embeddings": embeddings, "products": products}

    if TfidfVectorizer is not None and cosine_similarity is not None:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(texts)
        return {"backend": "tfidf", "texts": texts, "embeddings": matrix, "vectorizer": vectorizer, "products": products}

    tokenized = [_tokenize(text) for text in texts]
    return {"backend": "counter", "texts": texts, "tokenized": tokenized, "products": products}


def semantic_similarity(text_a: str, text_b: str) -> float:
    model = _get_model()
    if model is not None and cosine_similarity is not None:
        emb = model.encode([text_a, text_b], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        score = float(cosine_similarity([emb[0]], [emb[1]])[0][0])
        return max(0.0, min(1.0, score))

    if TfidfVectorizer is not None and cosine_similarity is not None:
        vec = TfidfVectorizer(ngram_range=(1, 2))
        mat = vec.fit_transform([text_a, text_b])
        score = float(cosine_similarity(mat[0], mat[1])[0][0])
        return max(0.0, min(1.0, score))

    return max(0.0, min(1.0, _cosine_counter(_tokenize(text_a), _tokenize(text_b))))


def semantic_search(query_text: str, products: List[Product], top_k: int = 20) -> List[Dict[str, object]]:
    bundle = build_product_embeddings(products)
    backend = bundle["backend"]
    texts = bundle["texts"]
    top_k = max(1, min(top_k, len(products)))

    if backend == "sentence_transformer":
        model = _get_model()
        assert model is not None
        query_embedding = model.encode([query_text], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        scores = cosine_similarity(query_embedding, bundle["embeddings"])[0]  # type: ignore[index]
        indices = np.argsort(scores)[::-1][:top_k] if np is not None else sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    elif backend == "tfidf":
        query_embedding = bundle["vectorizer"].transform([query_text])
        scores = cosine_similarity(query_embedding, bundle["embeddings"])[0]
        indices = np.argsort(scores)[::-1][:top_k] if np is not None else sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    else:
        query_tokens = _tokenize(query_text)
        scores = [_cosine_counter(query_tokens, tokens) for tokens in bundle["tokenized"]]
        indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    results: List[Dict[str, object]] = []
    for idx in indices:
        i = int(idx)
        results.append({"product": products[i], "semantic_score": float(scores[i]), "search_text": texts[i]})
    return results


class SemanticProductSearch:
    def __init__(self, products: List[Product]) -> None:
        self.products = products

    def search(self, query: str, top_k: int = 20) -> List[Dict[str, object]]:
        return semantic_search(query, self.products, top_k=top_k)

