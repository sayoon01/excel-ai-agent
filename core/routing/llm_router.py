"""LLM 기반 DSL 라우터 — 사용자 자연어를 DSL pipeline으로 변환.

흐름:
    사용자 prompt
       ↓
    [Prompt Enhancer]  ← 파일 스키마 + op 명세 + few-shot 주입
       ↓
    [LLM 호출]         ← function calling 또는 JSON mode
       ↓
    [JSON 파싱]
       ↓
    [schema validate] (core.dsl.spec.validate_pipeline)
       ↓
    DSL pipeline 반환

LLM 출력 형식 (function calling):
    {"name": "build_pipeline",
     "arguments": {
       "pipeline": [...],
       "explanation": "사용자 의도 요약"
     }}

설계 원칙:
- LLM은 코드 생성 X, DSL JSON만 출력
- 환각 차단을 위해 실제 파일·컬럼 정보를 system prompt에 명시
- few-shot은 최대 5개, 세션별 RAG (Phase 4에서 추가)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from core.dsl.spec import OPS, validate_pipeline, validate_pipeline_with_data, PipelineError


# ── LLM에 노출할 단일 "build_pipeline" 함수 ──────────────────────────────────
PIPELINE_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "build_pipeline",
        "description": (
            "사용자의 데이터 처리 요청을 DSL pipeline으로 변환한다. "
            "코드(Python/pandas)는 절대 생성하지 않고 JSON pipeline만 만든다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline": {
                    "type": "array",
                    "description": "실행 순서대로의 op 목록",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "description": "op 이름 (load/filter/sort/select/aggregate/chart/save 등)"},
                        },
                        "required": ["op"],
                    },
                },
                "explanation": {
                    "type": "string",
                    "description": "사용자 의도를 한 줄로 요약 (한국어)",
                },
            },
            "required": ["pipeline"],
        },
    },
}


# ── Prompt 구성 ──────────────────────────────────────────────────────────────

def _format_files_schema(files_info: list[dict]) -> str:
    """파일 목록과 각 파일의 컬럼·dtype·샘플을 텍스트로."""
    if not files_info:
        return "(파일 없음)"

    blocks = []
    for fi in files_info:
        name = fi.get("name", "?")
        cols = fi.get("col_names") or fi.get("columns") or []
        dtypes = fi.get("col_types") or fi.get("dtypes") or {}
        rows = fi.get("rows", "?")

        col_lines = []
        for c in list(cols)[:30]:  # 너무 길면 잘림
            dt = dtypes.get(c, "?") if isinstance(dtypes, dict) else "?"
            col_lines.append(f"    - {c} ({dt})")
        more = f"\n    ... +{len(cols) - 30}개" if len(cols) > 30 else ""

        blocks.append(
            f"- {name} ({rows}행 × {len(cols)}컬럼)\n"
            f"{chr(10).join(col_lines)}{more}"
        )
    return "\n".join(blocks)


def _format_ops_summary() -> str:
    """사용 가능한 op 목록과 인자를 LLM에 노출."""
    lines = []
    for op_name, spec in OPS.items():
        args = []
        for arg_name, arg_spec in spec.get("args", {}).items():
            tag = arg_name
            if arg_spec.get("required"):
                tag += "*"
            if "enum" in arg_spec:
                tag += f"({'/'.join(arg_spec['enum'])})"
            elif "type" in arg_spec:
                tag += f":{arg_spec['type']}"
            args.append(tag)
        lines.append(
            f"- {op_name}: {spec.get('description', '')}\n"
            f"  인자: {', '.join(args) if args else '(없음)'}"
        )
    return "\n".join(lines)


def _format_few_shot(examples: list[dict]) -> str:
    """과거 성공 사례를 few-shot 형태로."""
    if not examples:
        return ""
    lines = ["\n## 유사 과거 사례 (참고용)"]
    for i, ex in enumerate(examples[:5], 1):
        q  = ex.get("question", "")[:80]
        pl = json.dumps(ex.get("pipeline"), ensure_ascii=False)[:300]
        lines.append(f"{i}. \"{q}\" → {pl}")
    return "\n".join(lines)


def build_system_prompt(
    files_info: list[dict],
    last_result_info: dict | None = None,
    few_shot: list[dict] | None = None,
) -> str:
    files_block = _format_files_schema(files_info)
    ops_block   = _format_ops_summary()
    fewshot     = _format_few_shot(few_shot or [])

    last_block = ""
    if last_result_info:
        last_block = (
            f"\n## 직전 결과 (use_last_result=true로 참조 가능)\n"
            f"- {last_result_info.get('rows', '?')}행 × "
            f"{last_result_info.get('columns', '?')}컬럼\n"
            f"- 컬럼: {', '.join(last_result_info.get('col_names', [])[:10])}"
        )

    return f"""너는 엑셀/CSV 데이터 처리 요청을 분석해 의도에 맞는 응답을 JSON으로 생성하는 라우터다.

## 응답 형식 — 반드시 아래 JSON 하나만 출력

3가지 intent 중 하나로 분류한 뒤 그에 맞는 필드만 채운다:

1. **intent="dsl"** — 데이터 처리/변환/저장/차트 요청
{{"intent": "dsl",
  "pipeline": [...DSL op 배열...],
  "explanation": "사용자 의도 한 줄 요약"}}

2. **intent="text"** — 데이터에 대한 설명·분석·의견·요약 요청
   (데이터 처리 없이 답변만 필요)
{{"intent": "text",
  "message": "한국어 분석/설명 답변"}}

3. **intent="ambiguous"** — 의도가 모호함
{{"intent": "ambiguous",
  "message": "왜 모호한지 + 가능한 해석 한국어로",
  "suggested": ["구체화 예시1", "구체화 예시2", "구체화 예시3"]}}

## 분류 가이드
- "행 수", "필터", "정렬", "합계", "차트", "저장", "통합" 등 명확한 작업 → **dsl**
- "어떻게 생각", "분석해줘", "왜", "설명", "흥미로운 거", "인사이트" → **text**
- 위 둘이 섞이거나 너무 모호하면 → **ambiguous**

## 엄격한 규칙
- Python 코드를 작성하지 마라.
- DSL 외 추가 텍스트(설명/주석) 금지. 위 JSON 한 객체만.
- 사용 가능한 파일명과 컬럼명만 사용하라. 추측 금지.
- 사용자 의도가 명확하지 않으면 ambiguous로 분류.

## 사용 가능한 파일
{files_block}
{last_block}

## 사용 가능한 op
{ops_block}
{fewshot}

## 중요 컨벤션
- **aggregate 결과 컬럼명**: value 컬럼은 `{{원본컬럼}}_{{func}}` 형식으로 자동 rename된다.
  예: aggregate(group_by=비목, value_columns=[가격], func=mean) → 결과 컬럼 [비목, 가격_mean]
  다음 step에서 정렬·필터할 때 반드시 rename된 이름을 사용한다.
- group_by 컬럼은 이름이 바뀌지 않는다.

## 출력 예시
1) "가격이 5000 이상인 행을 비싼 순으로 상위 5개만"
   pipeline=[
     {{"op": "load"}},
     {{"op": "filter", "column": "가격", "operator": "gte", "value": 5000}},
     {{"op": "sort", "column": "가격", "direction": "desc"}},
     {{"op": "filter", "column": "가격", "operator": "top_n", "n": 5}}
   ]
2) "비목별 평균을 당년도집행 큰 순으로"
   pipeline=[
     {{"op": "load"}},
     {{"op": "aggregate", "group_by": "비목", "value_columns": ["당년도집행"], "func": "mean"}},
     {{"op": "sort", "column": "당년도집행_mean", "direction": "desc"}}
   ]
2b) "비목별 당년도집행 평균과 합계, 계획예산 합계"
    (컬럼마다 다른 func은 metrics 사용 — 권장)
    pipeline=[
      {{"op": "load"}},
      {{"op": "aggregate", "group_by": "비목",
        "metrics": [
          {{"column": "당년도집행", "func": "mean"}},
          {{"column": "당년도집행", "func": "sum"}},
          {{"column": "계획예산",   "func": "sum"}}
        ]}}
    ]
    → 결과 컬럼: [비목, 당년도집행_mean, 당년도집행_sum, 계획예산_sum]
3) "계획예산 대비 당년도집행 차이가 큰 비목 5개"
   (파생 컬럼 → calculate 사용. abs_diff = |A - B|)
   pipeline=[
     {{"op": "load"}},
     {{"op": "calculate", "left": "계획예산", "right": "당년도집행",
       "operator": "abs_diff", "name": "차이"}},
     {{"op": "sort", "column": "차이", "direction": "desc"}},
     {{"op": "filter", "column": "차이", "operator": "top_n", "n": 5}}
   ]
4) "집행률(당년도집행/당년도예산) 낮은 순"
   pipeline=[
     {{"op": "load"}},
     {{"op": "calculate", "left": "당년도집행", "right": "당년도예산",
       "operator": "percent", "name": "집행률"}},
     {{"op": "sort", "column": "집행률", "direction": "asc"}}
   ]
"""


# ── LLM 호출 ─────────────────────────────────────────────────────────────────

@dataclass
class RouterResult:
    """라우터 결과 — intent에 따라 채워지는 필드가 다름.

    intent="dsl":       pipeline + explanation
    intent="text":      message
    intent="ambiguous": message + suggested
    error 있으면 사용자에게 안내 메시지로 표시.
    """
    intent:       str                          # "dsl" | "text" | "ambiguous"
    pipeline:     list[dict] | None = None
    explanation:  str = ""
    message:      str = ""
    suggested:    list[str] | None = None
    raw_response: str = ""
    error:        str | None = None
    suggestion:   str | None = None            # 사용자에게 줄 수정 제안

    def ok(self) -> bool:
        if self.error:
            return False
        if self.intent == "dsl":
            return self.pipeline is not None
        return bool(self.message)


def route(
    prompt: str,
    files_info: list[dict],
    llm_client,
    last_result_info: dict | None = None,
    few_shot: list[dict] | None = None,
) -> RouterResult:
    """사용자 prompt → intent 분류 + 의도별 응답.

    policy (사용자 정의):
    1. intent 분류 (text/dsl/ambiguous) 후 분기
    2. text → 그대로 답변
    3. dsl 인데 JSON 깨짐 → repair 1회
    4. repair 실패 → 친절한 에러 (code fallback 금지)
    5. ambiguous → 답변 + 실행 후보 제안
    """
    system = build_system_prompt(files_info, last_result_info, few_shot)
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = _call_with_tools(llm_client, messages, system)
    except (NotImplementedError, AttributeError):
        raw = _call_with_json(llm_client, messages, system)

    # 1) JSON 파싱
    data, parse_err = _parse_router_response(raw)

    # 2) JSON 못 만들었으면 repair 1회 시도 (code fallback 금지)
    if data is None:
        data = _repair_json_response(raw)

    if data is None:
        # JSON 추출 완전 실패 — LLM이 자연어로 답변했을 가능성
        # 응답이 어느 정도 길고 한국어 위주면 text로 간주
        if _looks_like_text_answer(raw):
            return RouterResult(intent="text", message=raw.strip(), raw_response=raw)
        return RouterResult(
            intent="dsl", raw_response=raw,
            error="작업 명령을 만들지 못했습니다.",
            suggestion="파일명, 기준 컬럼, 계산 방식을 더 명확히 입력해 주세요.",
        )

    intent = (data.get("intent") or "").lower() or "dsl"  # 기본은 dsl

    if intent == "text":
        return RouterResult(
            intent="text",
            message=data.get("message", "").strip() or raw.strip(),
            raw_response=raw,
        )

    if intent == "ambiguous":
        return RouterResult(
            intent="ambiguous",
            message=data.get("message", "").strip() or raw.strip(),
            suggested=data.get("suggested") or [],
            raw_response=raw,
        )

    # intent == "dsl"
    pipeline = data.get("pipeline")
    if not isinstance(pipeline, list) or not pipeline:
        return RouterResult(
            intent="dsl", raw_response=raw,
            error="DSL pipeline이 비어있습니다.",
            suggestion="구체적인 작업(필터·정렬·집계 등)을 한 문장으로 명확히 표현해 주세요.",
        )

    try:
        validate_pipeline_with_data(pipeline, files_info)
    except PipelineError as e:
        return RouterResult(
            intent="dsl", raw_response=raw, pipeline=None,
            error=f"검증 실패: {e}",
            suggestion="파일·컬럼명을 확인하거나 표현을 더 명확히 해 주세요.",
        )

    return RouterResult(
        intent="dsl",
        pipeline=pipeline,
        explanation=data.get("explanation", ""),
        raw_response=raw,
    )


# 이전 API 호환 (기존 호출자가 있으면 동작 유지)
def route_to_pipeline(*args, **kwargs) -> RouterResult:
    return route(*args, **kwargs)


def _call_with_tools(llm_client, messages, system) -> str:
    """function calling 지원 클라이언트에 도구 1개(build_pipeline) 전달.

    현재 LLMClient는 chat_stream만 노출 — Phase별로 chat_with_tools 추가 예정.
    지금은 NotImplementedError를 던져서 JSON fallback으로 보냄.
    """
    raise NotImplementedError("chat_with_tools 미구현 — JSON mode fallback")


def _call_with_json(llm_client, messages, system) -> str:
    """JSON 출력 강제 — 시스템 프롬프트에 JSON 출력 지시 추가."""
    extra = (
        "\n\n## 출력 형식 (function calling 대신 JSON으로)\n"
        '아래 형식의 JSON 객체 하나만 출력하라. 다른 텍스트 금지.\n'
        '{"pipeline": [{"op": "..."}, ...], "explanation": "..."}'
    )
    full_system = system + extra
    return "".join(llm_client.chat_stream(messages, full_system))


def _parse_router_response(raw: str) -> tuple[dict | None, str | None]:
    """LLM 응답에서 라우터 JSON dict 추출 (intent/pipeline/message/...)."""
    # 1) ```json ... ``` 코드 펜스 안
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    candidate = m.group(1) if m else raw

    # 2) 첫 { ... } 객체
    obj_match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if not obj_match:
        return None, "JSON 객체 없음"

    try:
        data = json.loads(obj_match.group(0))
    except json.JSONDecodeError as e:
        return None, f"JSON 파싱 실패: {e}"

    if "arguments" in data and isinstance(data["arguments"], dict):
        data = data["arguments"]
    return data, None


def _repair_json_response(raw: str) -> dict | None:
    """JSON 깨짐을 정규식 휴리스틱으로 1회 복구 시도. 추가 LLM 호출 없음.

    흔한 패턴:
    - trailing comma (,]/,})
    - single quotes
    - 닫는 괄호 누락
    - JSON 객체 앞뒤에 자연어
    """
    m = re.search(r"\{.*", raw, re.DOTALL)  # 첫 { 부터 끝까지
    if not m:
        return None
    text = m.group(0)

    # 1) trailing comma 제거
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # 2) 단일 quote → 이중 quote (key·value 둘 다, 안전한 경우만)
    #    이미 이중인 곳은 영향 X, 한국어 문자열 내부는 보존을 위해 보수적 적용
    text2 = re.sub(r"(?<![\\])'([^'\n]*?)'(?=\s*[:,}\]])", r'"\1"', text)

    # 3) 닫는 괄호 균형 — 부족분만 채움
    open_b, close_b = text2.count("{"), text2.count("}")
    open_s, close_s = text2.count("["), text2.count("]")
    text2 += "]" * max(0, open_s - close_s)
    text2 += "}" * max(0, open_b - close_b)

    for candidate in (text2, text):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _looks_like_text_answer(raw: str) -> bool:
    """JSON 추출 실패 시 LLM이 자연어 답변을 한 것인지 판단.

    휴리스틱: 한글 문장 패턴이 일정 비율 이상이고 { 또는 [가 거의 없으면 text.
    """
    if not raw or len(raw.strip()) < 20:
        return False
    if raw.count("{") + raw.count("[") > 2:
        return False
    # 한글 문자 비율
    korean = sum(1 for c in raw if "가" <= c <= "힣")
    return korean / max(len(raw), 1) > 0.2
