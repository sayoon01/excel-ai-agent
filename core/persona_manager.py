"""페르소나 JSON CRUD 및 intent 매핑 매니저."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_PERSONA_FILE = Path(__file__).resolve().parent.parent / "data" / "personas.json"


def _load() -> dict:
    if _PERSONA_FILE.exists():
        return json.loads(_PERSONA_FILE.read_text(encoding="utf-8"))
    return {"personas": {}, "default_persona": "analyst", "intent_fallback": "analyst"}


def _save(data: dict) -> None:
    _PERSONA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PERSONA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_personas() -> dict[str, dict]:
    return _load()["personas"]


def get_persona(key: str) -> dict | None:
    return _load()["personas"].get(key)


def create_persona(
    key: str,
    name: str,
    about: str,
    response_style: str,
    system_prompt: str,
    description: str = "",
    intents: list[str] | None = None,
) -> dict:
    data = _load()
    if key in data["personas"]:
        raise ValueError(f"'{key}' 키가 이미 존재합니다.")
    now = datetime.now().isoformat()
    persona = {
        "name": name,
        "description": description or name,
        "type": "custom",
        "about": about,
        "response_style": response_style,
        "system_prompt": system_prompt,
        "intents": intents or [],
        "created_at": now,
        "updated_at": now,
    }
    data["personas"][key] = persona
    _save(data)
    return persona


def update_persona(key: str, **fields) -> dict:
    data = _load()
    if key not in data["personas"]:
        raise KeyError(f"'{key}' 페르소나를 찾을 수 없습니다.")
    persona = data["personas"][key]
    allowed = {"name", "description", "about", "response_style", "system_prompt", "intents"}
    for field, value in fields.items():
        if field in allowed:
            persona[field] = value
    persona["updated_at"] = datetime.now().isoformat()
    data["personas"][key] = persona
    _save(data)
    return persona


def delete_persona(key: str) -> bool:
    data = _load()
    persona = data["personas"].get(key)
    if not persona:
        return False
    if persona["type"] == "preset":
        raise PermissionError("프리셋 페르소나는 삭제할 수 없습니다.")
    del data["personas"][key]
    _save(data)
    return True


def duplicate_persona(source_key: str, new_key: str, new_name: str) -> dict:
    source = get_persona(source_key)
    if not source:
        raise KeyError(f"'{source_key}' 페르소나를 찾을 수 없습니다.")
    return create_persona(
        key=new_key,
        name=new_name,
        about=source["about"],
        response_style=source["response_style"],
        system_prompt=source["system_prompt"],
        description=source["description"],
        intents=[],
    )


# ── Intent 매핑 ───────────────────────────────────────────────────────────────

def resolve_persona_key(intent: str) -> str:
    """intent에 매핑된 페르소나 키 반환. 매핑 없으면 fallback."""
    data = _load()
    for key, persona in data["personas"].items():
        if intent in persona.get("intents", []):
            return key
    return data.get("intent_fallback", "analyst")
