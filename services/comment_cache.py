"""Persistent LLM comment cache backed by a JSON file in results/."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from services.file_manager import RESULT_DIR

_CACHE_FILE = RESULT_DIR / "llm_comments_cache.json"


def _profile_hash(profile: dict) -> str:
    return hashlib.md5(
        json.dumps(profile, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]


def make_key(fname: str, profile: dict) -> str:
    return f"{fname}::{_profile_hash(profile)}"


def load_comment(key: str) -> str | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return data.get(key)
    except Exception:
        return None


def save_comment(key: str, comment: str) -> None:
    data: dict = {}
    if _CACHE_FILE.exists():
        try:
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[key] = comment
    _CACHE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
