"""Few-shot example RAG store — 코사인 유사도 기반 동적 예시 검색."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from core.rag.embedder import Embedder, KeywordEmbedder

_RAG_DIR = Path(".rag")
_CACHE_PATH = _RAG_DIR / "embedding_cache.json"
_CUSTOM_PATH = _RAG_DIR / "custom_examples.json"


class ExampleStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []
        self._matrix: np.ndarray | None = None  # (N, D) L2-정규화
        self._embedder: Embedder | None = None
        self._ready = False

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def build(self, embedder: Embedder) -> None:
        """corpus 로드 + 임베딩 계산. API 기반 embedder는 캐시로 호출 최소화."""
        from core.prompts.examples import EXAMPLE_CORPUS

        _RAG_DIR.mkdir(exist_ok=True)
        all_entries = EXAMPLE_CORPUS + self._load_custom()
        is_keyword = isinstance(embedder, KeywordEmbedder)

        if is_keyword:
            # Keyword: vocab이 corpus 전체에 의존 → 캐시 없이 매번 재계산
            queries = [e["query"] for e in all_entries]
            embedder.fit(queries)
            vectors = embedder.embed(queries)
        else:
            # API 기반: content hash로 캐시 → 변경된 항목만 API 호출
            cache = self._load_cache()
            ekey = embedder.name
            vectors: list[list[float] | None] = [None] * len(all_entries)
            to_embed: list[tuple[int, str]] = []

            for i, entry in enumerate(all_entries):
                cached = cache.get(ekey, {}).get(_hash(entry["query"]))
                if cached:
                    vectors[i] = cached
                else:
                    to_embed.append((i, entry["query"]))

            if to_embed:
                try:
                    embs = embedder.embed([q for _, q in to_embed])
                    ec = cache.setdefault(ekey, {})
                    for (i, _), emb in zip(to_embed, embs):
                        ec[_hash(all_entries[i]["query"])] = emb
                        vectors[i] = emb
                    self._save_cache(cache)
                except Exception:
                    # API 실패 → keyword fallback
                    kb = KeywordEmbedder()
                    queries = [e["query"] for e in all_entries]
                    kb.fit(queries)
                    vectors = kb.embed(queries)
                    embedder = kb

            # None 슬롯을 keyword로 채움 (캐시에 없는데 API도 실패한 경우)
            missing = [i for i, v in enumerate(vectors) if v is None]
            if missing:
                kb = KeywordEmbedder()
                kb.fit([all_entries[i]["query"] for i in missing])
                embs = kb.embed([all_entries[i]["query"] for i in missing])
                for i, emb in zip(missing, embs):
                    vectors[i] = emb

        mat = np.array(vectors, dtype=float)
        if mat.ndim == 2 and len(mat) > 0:
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            self._matrix = mat / np.where(norms > 0, norms, 1.0)
        else:
            self._matrix = None

        self._entries = all_entries
        self._embedder = embedder
        self._ready = True

    def ensure_built(self, embedder: Embedder) -> None:
        """embedder가 바뀌었거나 미초기화 상태면 rebuild."""
        if not self._ready or (
            self._embedder is not None and self._embedder.name != embedder.name
        ):
            self.build(embedder)

    def retrieve(self, query: str, intent: str = "", k: int = 2) -> list[dict]:
        """쿼리와 가장 유사한 k개 예시 반환. 실패 시 intent 기반 정적 fallback."""
        if not self._ready or self._matrix is None or not query.strip():
            return self._static_fallback(intent, k)

        try:
            vec = np.array(self._embedder.embed([query])[0], dtype=float)
        except Exception:
            return self._static_fallback(intent, k)

        norm = np.linalg.norm(vec)
        vec = vec / norm if norm > 0 else vec

        scores = self._matrix @ vec  # cosine similarity (N,)

        # 같은 intent면 +0.1 보너스 (의미유사도 + intent 정확도 혼합)
        intent_bonus = np.array(
            [0.1 if e.get("intent") == intent else 0.0 for e in self._entries]
        )
        scores = scores + intent_bonus

        top_k = min(k, len(self._entries))
        top_indices = np.argsort(scores)[::-1][:top_k].tolist()
        return [self._entries[i] for i in top_indices]

    def add(self, query: str, intent: str, code: str, files_info: list[dict]) -> None:
        """성공 케이스 추가 — 파일명 정규화 후 corpus + 캐시에 반영."""
        if not self._ready or not self._embedder:
            return

        entry_id = f"custom_{_hash(query)[:8]}"
        if any(e["id"] == entry_id for e in self._entries):
            return  # 중복

        entry = {
            "id": entry_id,
            "intent": intent,
            "query": query,
            "tags": ["user_generated"],
            "template": _normalize_code(code, files_info),
            "source": "custom",
        }

        try:
            if isinstance(self._embedder, KeywordEmbedder):
                # Keyword: vocab을 새 쿼리 포함해 재피팅
                all_queries = [e["query"] for e in self._entries] + [query]
                self._embedder.fit(all_queries)
                all_embs = self._embedder.embed(all_queries)
                mat = np.array(all_embs, dtype=float)
                norms = np.linalg.norm(mat, axis=1, keepdims=True)
                self._entries.append(entry)
                self._matrix = mat / np.where(norms > 0, norms, 1.0)
            else:
                vec = self._embedder.embed([query])[0]
                vec_arr = np.array(vec, dtype=float)
                norm = np.linalg.norm(vec_arr)
                vec_norm = (vec_arr / norm if norm > 0 else vec_arr).reshape(1, -1)
                self._entries.append(entry)
                self._matrix = (
                    np.vstack([self._matrix, vec_norm])
                    if self._matrix is not None
                    else vec_norm
                )
                # 캐시 업데이트
                cache = self._load_cache()
                cache.setdefault(self._embedder.name, {})[_hash(query)] = vec
                self._save_cache(cache)
        except Exception:
            self._entries.append(entry)  # 임베딩 실패해도 entry는 저장

        self._save_custom(entry)

    def is_ready(self) -> bool:
        return self._ready

    # ── private ───────────────────────────────────────────────────────────────

    def _static_fallback(self, intent: str, k: int) -> list[dict]:
        from core.prompts.examples import EXAMPLE_CORPUS
        hits = [e for e in EXAMPLE_CORPUS if e.get("intent") == intent]
        return (hits or EXAMPLE_CORPUS)[:k]

    def _load_custom(self) -> list[dict]:
        if not _CUSTOM_PATH.exists():
            return []
        try:
            return json.loads(_CUSTOM_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _load_cache(self) -> dict:
        if not _CACHE_PATH.exists():
            return {}
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self, cache: dict) -> None:
        try:
            _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _save_custom(self, entry: dict) -> None:
        existing = self._load_custom()
        existing.append(entry)
        try:
            _CUSTOM_PATH.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


# ── 모듈 레벨 singleton ───────────────────────────────────────────────────────

_store: ExampleStore | None = None


def get_store() -> ExampleStore:
    global _store
    if _store is None:
        _store = ExampleStore()
    return _store


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _normalize_code(code: str, files_info: list[dict]) -> str:
    """파일명을 {FILE_A}/{FILE_B} placeholder로 치환. 컬럼명은 유지(LLM이 적응)."""
    result = code
    letters = "ABCDEFGH"
    for i, f in enumerate(files_info[:8]):
        name = f.get("name", "")
        if not name:
            continue
        for q in ('"', "'"):
            result = result.replace(f"{q}{name}{q}", f'{q}{{FILE_{letters[i]}}}{q}')
    return result
