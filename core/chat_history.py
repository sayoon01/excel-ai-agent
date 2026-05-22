"""채팅 세션 영속성 — JSON 파일 기반 저장/로드/목록/삭제."""
from __future__ import annotations

import json
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
