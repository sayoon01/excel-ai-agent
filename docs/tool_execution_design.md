# Tool 실행 아키텍처 설계

## 현재 구조 (Rule-based Tool Dispatch)

```
사용자 입력
    ↓
Rule Router (키워드 기반, LLM 없음)
    ↓  confidence >= 0.8
dispatch_tool(tool_name, files_info, prompt)
    ↓
툴 내부에서 파라미터 직접 파싱 (휴리스틱)
    ↓
DataFrame / 숫자 / 차트 출력 (LLM 해석 없음)
```

**문제점**
- 결과 해석이 없음 — "16행 추출됨" 같은 기계적 요약만 나옴
- 파라미터 추출이 휴리스틱 — "매출 1000 이상" 같은 표현을 툴 내부에서 직접 파싱
- 사용자 질문에 맞는 맥락 있는 답변 불가

---

## 선택지 A — Full Function Calling

LLM이 tool 선택과 파라미터 추출까지 담당, 결과도 LLM이 해석.

```
사용자 입력
    ↓
LLM 호출 (tool schema 전달)
    ↓
LLM 응답 (JSON):
  {"tool": "filter_rows", "column": "매출", "operator": ">=", "value": 1000}
    ↓
filter_rows(column="매출", operator=">=", value=1000)
    ↓
결과 → LLM에 전달
    ↓
"매출 1,000 이상인 행은 16건입니다. 최댓값은 X, 상위 항목은 Y입니다."
    ↓
사용자 표시
```

### Tool Schema 예시 (OpenAI function calling 형식)

```python
TOOL_SCHEMAS = [
    {
        "name": "filter_rows",
        "description": "조건에 맞는 행을 필터링한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "column":   {"type": "string", "description": "필터 기준 컬럼명"},
                "operator": {"type": "string", "enum": [">", ">=", "<", "<=", "==", "!=", "contains"]},
                "value":    {"description": "비교값 (숫자 또는 문자열)"},
            },
            "required": ["column", "operator", "value"],
        },
    },
    {
        "name": "aggregate_data",
        "description": "그룹별 합계·평균·최대·최소를 계산한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "description": "집계 기준 컬럼명"},
                "column":   {"type": "string", "description": "집계 대상 컬럼명"},
                "agg":      {"type": "string", "enum": ["sum", "mean", "max", "min", "count"]},
            },
            "required": ["column", "agg"],
        },
    },
    # ... 나머지 툴
]
```

### 실행 흐름 코드 스케치

```python
def run_function_calling(prompt, files_info, client):
    # 1. LLM에게 tool schema + 질문 전달
    tool_call = client.chat_with_tools(
        messages=[{"role": "user", "content": prompt}],
        tools=TOOL_SCHEMAS,
        file_context=build_file_context(files_info),
    )

    # 2. LLM이 선택한 툴 + 파라미터로 실행
    result = dispatch_tool(
        tool_call["tool"],
        files_info,
        **tool_call["params"],   # {"column": "매출", "operator": ">=", "value": 1000}
    )

    # 3. 결과를 LLM에게 전달해 최종 답변 생성
    result_summary = format_result_for_llm(result)
    final_answer = client.chat([
        {"role": "user",      "content": prompt},
        {"role": "assistant", "content": f"[tool: {tool_call['tool']}]"},
        {"role": "tool",      "content": result_summary},
    ])

    return final_answer, result
```

**장점**
- 파라미터 추출 정확도 최고 (LLM이 직접 구조화)
- 툴 내부 파싱 로직 불필요 → 툴 단순화
- 결과에 대한 맥락 있는 해석 제공
- 멀티스텝 체이닝 자연스럽게 지원

**단점**
- LLM 2회 호출 → 속도·비용 2배
- Ollama 모델 중 function calling 미지원 모델 있음
- tool schema 정의·유지 비용

---

## 선택지 B — 현재 라우터 유지 + LLM 결과 해석 추가 (Hybrid)

라우팅은 빠른 rule 기반으로 유지, 실행 결과만 LLM이 해석.

```
사용자 입력
    ↓
Rule Router (LLM 없음, 빠름)
    ↓
dispatch_tool()  ← 기존 휴리스틱 파라미터 추출 유지
    ↓
결과 요약 생성 (행 수, 주요 수치, 컬럼 등)
    ↓
LLM 호출 1회:
  "사용자 질문: {prompt}
   실행 툴: filter_rows
   결과: 16행, 최대 매출 5,200만, 평균 1,840만 ...
   → 사용자에게 한국어로 설명해줘"
    ↓
"매출 1,000만 이상인 항목은 총 16건이며, 최고 매출은 5,200만입니다."
    ↓
사용자 표시
```

### 결과 요약 생성 예시

```python
def build_result_summary(result: dict, prompt: str) -> str:
    if result["type"] == "dataframe":
        df = result["value"]
        num_cols = df.select_dtypes(include="number").columns.tolist()
        stats = {c: {"max": df[c].max(), "mean": df[c].mean()} for c in num_cols[:3]}
        return (
            f"사용자 질문: {prompt}\n"
            f"실행 결과: {len(df)}행 × {len(df.columns)}열\n"
            f"주요 수치: {stats}\n"
            f"상위 3행:\n{df.head(3).to_string(index=False)}"
        )
    if result["type"] == "number":
        return f"사용자 질문: {prompt}\n계산 결과: {result['value']:,}"
    return f"사용자 질문: {prompt}\n결과: {result.get('label', '')}"
```

**장점**
- LLM 1회만 추가 → 속도·비용 부담 낮음
- Ollama 포함 모든 프로바이더 지원 (function calling 불필요)
- 기존 코드 변경 최소화 (dispatch_tool 그대로)
- 사용자 불만의 핵심("결과 해석 없음") 해소

**단점**
- 파라미터 추출은 여전히 휴리스틱
- 복잡한 조건은 여전히 오분류 가능성

---

## 권장 구현 순서

### Phase 1 — 선택지 B (빠른 개선)

tool 모드 실행 후 LLM 결과 해석 단계 추가.

```
수정 파일:
- pages/0_채팅.py     : tool 실행 후 LLM interpret 호출
- core/tools/result_interpreter.py  : 결과 요약 빌더 (신규)
```

### Phase 2 — 선택지 A (정밀 개선)

OpenAI/Gemini는 native function calling, Ollama는 JSON 모드로 대체.

```
수정 파일:
- core/tools/schemas.py             : tool schema 정의 (신규)
- core/llm/llm_client.py            : chat_with_tools() 메서드 추가
- core/routing/task_router.py       : LLM 분류 2차에서 function call로 교체
- core/tools/dispatcher.py          : 구조화된 파라미터 받도록 시그니처 변경
```

---

## 프로바이더별 Function Calling 지원 현황

| 프로바이더 | 지원 방식 | 비고 |
|---|---|---|
| OpenAI (GPT-4o 등) | Native function calling | 안정적, JSON 보장 |
| Gemini | Native tool use | 안정적 |
| Ollama | 모델마다 다름 | llama3, mistral 등 일부만 지원. JSON 모드로 대체 가능 |

Ollama 대응: `chat_with_tools()` 내부에서 function calling 미지원 모델이면 system prompt에 schema를 텍스트로 넣고 JSON 응답 파싱으로 폴백.

```python
def chat_with_tools(self, messages, tools, ...):
    if self._supports_function_calling():
        return self._native_tool_call(messages, tools)
    else:
        # JSON 모드 폴백
        schema_text = json.dumps(tools, ensure_ascii=False, indent=2)
        system = f"아래 스키마 중 하나를 선택해 JSON으로만 응답하세요:\n{schema_text}"
        raw = self.chat_stream(messages, system)
        return parse_tool_json(raw)
```
