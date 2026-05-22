"""시스템 프롬프트·사용자 프롬프트 조립."""
from __future__ import annotations

from core.persona_manager import get_persona, resolve_persona_key
from core.prompts.code_rules import CODE_RULES
from core.prompts.examples import EXAMPLES

_DTYPE_LABEL: dict[str, str] = {
    "int":       "정수",
    "float":     "실수",
    "bool":      "불리언",
    "datetime":  "날짜",
    "timedelta": "기간",
    "category":  "카테고리",
    "object":    "문자열",
    "string":    "문자열",
}


def _dtype_label(dtype_str: str, is_mixed: bool = False) -> str:
    if is_mixed:
        return "혼합(수치)"
    s = str(dtype_str).lower()
    for prefix, label in _DTYPE_LABEL.items():
        if s.startswith(prefix):
            return label
    return ""


def _fmt_num(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _summarize_files(files_info: list[dict]) -> str:
    if not files_info:
        return "현재 업로드된 파일이 없습니다."
    lines = []
    for f in files_info:
        null_cols = [
            f"{col}({cnt}개)"
            for col, cnt in f.get("null_counts", {}).items()
            if cnt > 0
        ]
        null_note = f" | 결측치: {', '.join(null_cols)}" if null_cols else ""

        dtypes = f.get("dtypes", {})
        mixed = set(f.get("mixed_type_cols", []))
        col_parts = []
        for col in f["col_names"]:
            label = _dtype_label(dtypes.get(col, ""), col in mixed)
            col_parts.append(f"{col}({label})" if label else col)

        lines.append(
            f"  - {f['name']} : {f['rows']}행 × {f['columns']}열"
            f" | 컬럼: {', '.join(col_parts)}{null_note}"
        )
        if f.get("head_sample"):
            first = f["head_sample"][0]
            pairs = [f"{k}={repr(v)}" for k, v in list(first.items())[:5]]
            lines.append(f"    샘플(1행): {', '.join(pairs)}")
        if f.get("numeric_stats"):
            parts = []
            for col, s in list(f["numeric_stats"].items())[:6]:
                parts.append(
                    f"{col}[min={_fmt_num(s['min'])} / "
                    f"평균={_fmt_num(s['mean'])} / "
                    f"max={_fmt_num(s['max'])}]"
                )
            lines.append(f"    수치형 통계: {', '.join(parts)}")
        if f.get("string_stats"):
            parts = []
            for col, s in list(f["string_stats"].items())[:5]:
                top_str = ", ".join(s["top"])
                parts.append(f"{col}({s['unique']}종: {top_str})")
            lines.append(f"    범주형 컬럼: {', '.join(parts)}")
    return "\n".join(lines)


def _format_recent_conversation(messages: list[dict], max_turns: int = 3) -> str:
    prior = messages[:-1]
    if not prior:
        return ""
    recent = prior[-(max_turns * 2):]
    lines = []
    for msg in recent:
        role = "사용자" if msg["role"] == "user" else "어시스턴트"
        content = msg.get("display", msg["content"])
        content = content[:150].replace("\n", " ").strip()
        lines.append(f"  {role}: {content}")
    return "\n".join(lines)


def _resolve_placeholders(text: str, files_info: list[dict]) -> str:
    file_a = files_info[0]["name"] if len(files_info) >= 1 else "파일.xlsx"
    file_b = files_info[1]["name"] if len(files_info) >= 2 else file_a
    return text.replace("{FILE_A}", file_a).replace("{FILE_B}", file_b)


def build_system_prompt(
    files_info: list[dict],
    intent: str = "query",
    compact: bool = False,
    last_result_info: dict | None = None,
    recent_messages: list[dict] | None = None,
    persona_key: str | None = None,
    mode: str = "code",
) -> str:
    _key = persona_key or resolve_persona_key(intent)
    p = get_persona(_key) or get_persona("analyst")
    persona = p["system_prompt"]

    file_section = f"## 현재 업로드된 파일\n{_summarize_files(files_info)}"
    parts = [persona, file_section]

    if last_result_info:
        cols = ", ".join(last_result_info["col_names"])
        parts.append(
            f"## 직전 작업 결과 (last_result 변수로 접근 가능)\n"
            f"  {last_result_info['rows']}행 × {last_result_info['columns']}열"
            f" | 컬럼: {cols}"
        )

    if recent_messages:
        conv = _format_recent_conversation(recent_messages)
        if conv:
            parts.append(f"## 이전 대화 맥락\n{conv}")

    # llm 모드: 자연어 답변만 — CODE_RULES/EXAMPLES 제외
    if mode == "llm":
        parts.append(
            "## 응답 방식\n"
            "코드 없이 자연어로 간결하게 답변하세요. "
            "파일 데이터를 참고해 구체적인 수치나 컬럼명을 언급하면 좋습니다."
        )
    else:
        example_mode = "compact" if compact else "full"
        raw_example = EXAMPLES.get(intent, EXAMPLES["query"])[example_mode]
        example = _resolve_placeholders(raw_example, files_info)
        parts.extend([example, CODE_RULES])

    return "\n\n".join(parts)


