"""공통 UI 조각 — 의도 배지, 응답 파싱."""
from __future__ import annotations

import re

_INTENT_BADGE_COLOR: dict[str, tuple[str, str]] = {
    "merge":     ("#DBEAFE", "#1E40AF"),
    "filter":    ("#DCFCE7", "#166534"),
    "aggregate": ("#FEF3C7", "#92400E"),
    "transform": ("#FEF9C3", "#854D0E"),
    "analyze":   ("#EDE9FE", "#5B21B6"),
    "export":    ("#F1F5F9", "#475569"),
    "query":     ("#F1F5F9", "#475569"),
}


def intent_badge_html(intent: str, label: str) -> str:
    bg, fg = _INTENT_BADGE_COLOR.get(intent, ("#1f2937", "#9ca3af"))
    return (
        f'<span style="background:{bg};color:{fg};'
        f'padding:2px 10px;border-radius:12px;'
        f'font-size:12px;font-weight:600;">'
        f'🏷 {label}</span>'
    )


def split_response(content: str) -> tuple[str, str]:
    """Returns (narrative_text, first_code_block). Strips code block from narrative."""
    code_match = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
    if not code_match:
        return content, ""
    narrative = re.sub(r"```python\s*\n.*?```", "", content, flags=re.DOTALL).strip()
    narrative = re.sub(r"\n{3,}", "\n\n", narrative)
    return narrative, code_match.group(1)
