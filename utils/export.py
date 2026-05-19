"""Chat history export utilities."""
from __future__ import annotations


def to_markdown(messages: list[dict]) -> str:
    lines = ["# Excel AI Platform - 대화 내보내기\n"]
    for msg in messages:
        role = "사용자" if msg["role"] == "user" else "AI"
        lines.append(f"## {role}\n\n{msg['content']}\n")
    return "\n".join(lines)
