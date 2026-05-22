"""Tool 실행 결과 인메모리 캐시.

캐시 키: (tool_name, files_snapshot, prompt_normalized)
  - files_snapshot : 파일명 + 수정시간 튜플 — 파일이 바뀌면 자동 무효화
  - prompt_normalized : 소문자 + 공백 정규화
TTL: 10분 (실험적 데이터 변경 주기를 감안한 값)
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from services.file_manager import UPLOAD_DIR

_CACHE: dict[str, tuple[dict, float]] = {}   # key → (result, expires_at)
_TTL = 600   # 10분


def _file_snapshot(files_info: list[dict]) -> str:
    """파일명 + 수정시간 해시 — 파일 변경 시 캐시 무효화."""
    parts = []
    for f in files_info:
        name = f.get("name", "")
        path = UPLOAD_DIR / name
        mtime = path.stat().st_mtime if path.exists() else 0
        parts.append(f"{name}:{mtime}")
    return "|".join(parts)


def _make_key(tool_name: str, files_info: list[dict], prompt: str) -> str:
    normalized = " ".join(prompt.lower().split())
    raw = f"{tool_name}||{_file_snapshot(files_info)}||{normalized}"
    return hashlib.md5(raw.encode()).hexdigest()


def get(tool_name: str, files_info: list[dict], prompt: str) -> dict | None:
    key = _make_key(tool_name, files_info, prompt)
    entry = _CACHE.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    if entry:
        del _CACHE[key]
    return None


def put(tool_name: str, files_info: list[dict], prompt: str, result: dict) -> None:
    key = _make_key(tool_name, files_info, prompt)
    _CACHE[key] = (result, time.time() + _TTL)


def invalidate_all() -> None:
    _CACHE.clear()


def cache_size() -> int:
    now = time.time()
    return sum(1 for _, exp in _CACHE.values() if now < exp)
