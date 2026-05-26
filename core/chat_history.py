"""채팅 세션 영속성 — JSON 파일 기반 저장/로드/목록/삭제."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_DIR = BASE_DIR / ".chat_history"
HISTORY_DIR.mkdir(exist_ok=True)


def new_chat_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_chat(chat_id: str, messages: list[dict]) -> None:
    if not chat_id or not messages:
        return
    path = HISTORY_DIR / f"{chat_id}.json"
    path.write_text(json.dumps({"messages": messages}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_chat(chat_id: str) -> list[dict]:
    path = HISTORY_DIR / f"{chat_id}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("messages", [])
    except Exception:
        return []


def list_chats() -> list[dict]:
    """최신순으로 정렬된 채팅 목록 반환. [{id, title, updated_at}]"""
    chats = []
    for p in sorted(HISTORY_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            messages = json.loads(p.read_text(encoding="utf-8")).get("messages", [])
            first_user = next((m for m in messages if m["role"] == "user"), None)
            title = (
                first_user.get("display", first_user["content"])[:28]
                if first_user else "새 대화"
            )
            chats.append({"id": p.stem, "title": title})
        except Exception:
            continue
    return chats


def delete_chat(chat_id: str) -> None:
    path = HISTORY_DIR / f"{chat_id}.json"
    if path.exists():
        path.unlink()


def search_history(query: str, max_results: int = 5) -> list[dict]:
    """키워드로 과거 성공 코드 쌍 검색.

    Returns: [{query, code, date, chat_id}] — 최신순, 코드 블록 있는 응답만.
    """
    keywords = [w for w in query.strip().split() if len(w) > 1]
    if not keywords:
        return []

    results: list[dict] = []
    paths = sorted(HISTORY_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

    for path in paths:
        try:
            messages = json.loads(path.read_text(encoding="utf-8")).get("messages", [])
        except Exception:
            continue

        for i, msg in enumerate(messages):
            if msg["role"] != "user" or i + 1 >= len(messages):
                continue

            user_text = msg.get("display", msg.get("content", ""))
            if not any(kw in user_text for kw in keywords):
                continue

            next_msg = messages[i + 1]
            if next_msg["role"] != "assistant":
                continue

            code_match = re.search(r"```python\s*\n(.*?)```", next_msg.get("content", ""), re.DOTALL)
            if not code_match:
                continue

            results.append({
                "query": user_text[:80],
                "code": code_match.group(1).strip(),
                "date": path.stem,
                "chat_id": path.stem,
            })

    # 쿼리 앞부분 기준 중복 제거
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        key = r["query"][:20]
        if key not in seen:
            seen.add(key)
            unique.append(r)
        if len(unique) >= max_results:
            break

    return unique
