"""Embedder 추상화 — OpenAI / Gemini / Keyword(numpy) fallback.

우선순위: OpenAI → Gemini → KeywordEmbedder(외부 의존성 없음)
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 리스트 → 임베딩 벡터 리스트."""

    @property
    @abstractmethod
    def name(self) -> str:
        """임베딩 캐시 키에 사용되는 식별자."""


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIEmbedder(Embedder):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [r.embedding for r in resp.data]


# ── Gemini ────────────────────────────────────────────────────────────────────

class GeminiEmbedder(Embedder):
    def __init__(self, api_key: str, model: str = "models/text-embedding-004"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model = model

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            r = self._genai.embed_content(
                model=self._model,
                content=text,
                task_type="retrieval_document",
            )
            result.append(r["embedding"])
        return result


# ── Keyword (numpy only, 외부 의존성 없음) ────────────────────────────────────

class KeywordEmbedder(Embedder):
    """한국어 문자 bigram TF-IDF — numpy만 사용, Ollama 환경 fallback."""

    def __init__(self):
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray = np.array([])
        self._fitted = False

    @property
    def name(self) -> str:
        return "keyword:bigram"

    def fit(self, corpus: list[str]) -> None:
        n = len(corpus)
        df: dict[str, int] = {}
        for doc in corpus:
            for ng in set(self._ngrams(doc)):
                df[ng] = df.get(ng, 0) + 1
        self._vocab = {ng: i for i, ng in enumerate(df)}
        df_arr = np.array([df[ng] for ng in self._vocab], dtype=float)
        self._idf = np.log((n + 1) / (df_arr + 1)) + 1
        self._fitted = True

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._fitted:
            self.fit(texts)
        result = []
        for text in texts:
            vec = np.zeros(len(self._vocab))
            for ng in self._ngrams(text):
                if ng in self._vocab:
                    vec[self._vocab[ng]] += 1
            vec = vec * self._idf
            norm = np.linalg.norm(vec)
            result.append((vec / norm if norm > 0 else vec).tolist())
        return result

    @staticmethod
    def _ngrams(text: str, n: int = 2) -> list[str]:
        return [text[i : i + n] for i in range(len(text) - n + 1)]
