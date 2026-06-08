"""LLM Function Calling용 도구 스펙 — OpenAI/Ollama 표준 형식.

설계 원칙:
- 모든 도구가 같은 의미는 같은 인자명 사용 (column/columns/value/func/direction 등)
- enum 값은 영문 ASCII, description은 한국어
- use_last_result는 체이닝 가능 도구에만 노출
- examples는 description 안에 한국어 한 줄로 포함

다른 프로바이더로 옮길 때:
  Anthropic: `function.parameters` → `input_schema`
  Gemini:    Tool / FunctionDeclaration 구조로 변환
"""
from __future__ import annotations


# ── 공통 enum 값 ──────────────────────────────────────────────────────────────
_OPERATORS = [
    "gte", "lte", "gt", "lt", "eq", "neq",
    "contains", "not_contains", "isna", "notna",
    "in_range",         # value(min) ≤ x ≤ value_max
    "top_n", "bottom_n",  # n 인자 사용
    "col_gt", "col_lt", "col_eq",  # compare_column 인자 사용
]

_AGG_FUNCS    = ["sum", "mean", "max", "min", "count", "median", "std"]
_DIRECTIONS   = ["asc", "desc"]
_CHART_TYPES  = ["bar", "line", "pie", "scatter", "histogram", "boxplot"]
_FILE_FORMATS = ["xlsx", "csv"]


# ── 13개 도구 스펙 ────────────────────────────────────────────────────────────

TOOL_SPECS: list[dict] = [
    # ── 1. 읽기/조회 도구 (no-arg) ───────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_row_count",
            "description": "각 파일의 행 수를 조회. 예: '각 파일 행 수 알려줘', '이 파일 몇 줄이야'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "특정 파일만 조회할 때 (기본: 전체)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_missing",
            "description": "각 파일·컬럼별 결측치 개수와 비율을 분석. 예: '결측치 분석해줘'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string", "description": "특정 파일만"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_profile",
            "description": "컬럼명·dtype·기본 통계·샘플을 보여주는 데이터 프로파일. 예: '어떤 컬럼이 있어?'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string", "description": "특정 파일만"},
                    "columns":   {"type": "array", "items": {"type": "string"},
                                  "description": "특정 컬럼만 (기본: 전체)"},
                },
            },
        },
    },

    # ── 2. 컬럼 선택 ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "select_columns",
            "description": "명시한 컬럼만 추출 (projection). 예: '비목분류만 보여줘', '이름, 부서, 연봉만'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "추출할 컬럼명 목록 (필수)",
                    },
                    "use_last_result": {
                        "type": "boolean", "default": False,
                        "description": "true면 직전 도구 결과를 입력으로 사용",
                    },
                },
                "required": ["columns"],
            },
        },
    },

    # ── 3. 필터 (가장 복잡한 도구) ───────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "filter_rows",
            "description": (
                "조건에 맞는 행만 추출. operator 종류:\n"
                "- 수치 비교: gte/lte/gt/lt/eq/neq (value 사용)\n"
                "- 범위: in_range (value=min, value_max=max)\n"
                "- 문자 포함: contains/not_contains (value=키워드)\n"
                "- 결측: isna/notna (value 불필요)\n"
                "- 컬럼 간 비교: col_gt/col_lt/col_eq (compare_column 사용)\n"
                "- 상위/하위 N개: top_n/bottom_n (n 사용)\n"
                "예: '가격이 10000 이상' → column=가격, operator=gte, value=10000"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {
                        "type": "string",
                        "description": "조건을 적용할 컬럼명. top_n/bottom_n에서는 정렬 기준 컬럼",
                    },
                    "operator": {
                        "type": "string", "enum": _OPERATORS,
                        "description": "비교 연산자 — 종류별 사용 인자는 description 참고",
                    },
                    "value": {
                        "description": "비교 값. 수치/문자열. operator가 isna/notna면 생략",
                    },
                    "value_max": {
                        "type": "number",
                        "description": "in_range의 상한값 (operator=in_range일 때만)",
                    },
                    "compare_column": {
                        "type": "string",
                        "description": "col_gt/col_lt/col_eq일 때 비교 대상 컬럼",
                    },
                    "n": {
                        "type": "integer",
                        "description": "top_n/bottom_n의 개수",
                    },
                    "use_last_result": {"type": "boolean", "default": False},
                },
                "required": ["column", "operator"],
            },
        },
    },

    # ── 4. 정렬 ──────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "sort_rows",
            "description": (
                "지정 컬럼 기준 정렬. direction=desc면 큰/높은 순. "
                "예: '당년도집행 큰 순' → column=당년도집행, direction=desc"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "column":    {"type": "string", "description": "정렬 기준 컬럼"},
                    "direction": {"type": "string", "enum": _DIRECTIONS, "default": "asc"},
                    "use_last_result": {"type": "boolean", "default": False},
                },
                "required": ["column"],
            },
        },
    },

    # ── 5. 집계 ──────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "aggregate_data",
            "description": (
                "수치 컬럼 집계. group_by 있으면 그룹별, 없으면 전체. "
                "예: '비목분류별 당년도집행 합계' → group_by=비목분류, "
                "value_columns=[당년도집행], func=sum"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_by": {
                        "type": "string",
                        "description": "그룹 키 컬럼 (없으면 전체 집계)",
                    },
                    "value_columns": {
                        "type": "array", "items": {"type": "string"},
                        "description": "집계할 수치 컬럼. 비우면 모든 수치 컬럼",
                    },
                    "func": {
                        "type": "string", "enum": _AGG_FUNCS, "default": "sum",
                    },
                    "use_last_result": {"type": "boolean", "default": False},
                },
            },
        },
    },

    # ── 6. 병합 ──────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "merge_files",
            "description": (
                "서로 다른 양식의 파일들을 공통 컬럼 기준으로 join. "
                "예: '두 파일을 사번 기준으로 조인'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key_columns": {
                        "type": "array", "items": {"type": "string"},
                        "description": "조인 키 컬럼 (없으면 공통 컬럼 자동 감지)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge_same_format",
            "description": (
                "같은 양식 파일 여러 개를 통합. 키 컬럼으로 그룹 묶고 수치는 평균. "
                "예: '월별 데이터 합쳐서 평균', '예실대비표 3개 통합'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key_columns": {
                        "type": "array", "items": {"type": "string"},
                        "description": "통합 키 컬럼 (없으면 텍스트 컬럼 자동 추론)",
                    },
                },
            },
        },
    },

    # ── 7. 차트 ──────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_chart",
            "description": (
                "차트 생성. chart_type 종류: bar/line/pie/scatter/histogram/boxplot. "
                "예: '비목별 당년도집행 막대' → chart_type=bar, x_column=비목분류, "
                "y_columns=[당년도집행]"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string", "enum": _CHART_TYPES, "default": "bar",
                    },
                    "x_column": {
                        "type": "string",
                        "description": "x축 컬럼 (보통 카테고리)",
                    },
                    "y_columns": {
                        "type": "array", "items": {"type": "string"},
                        "description": "y축 컬럼 (수치, 다중 시리즈 가능)",
                    },
                    "use_last_result": {"type": "boolean", "default": False},
                },
                "required": ["chart_type"],
            },
        },
    },

    # ── 8. 저장 ──────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "export_data",
            "description": "결과를 파일로 저장. 예: '엑셀로 저장', 'csv로 내보내줘'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format":   {"type": "string", "enum": _FILE_FORMATS, "default": "xlsx"},
                    "filename": {"type": "string",
                                 "description": "선택. 비우면 자동 생성"},
                    "use_last_result": {"type": "boolean", "default": True},
                },
            },
        },
    },

    # ── 9. 합성 도구 — 기존 호환을 위한 단순 wrapper ──────────────────────────
    # (ReAct 단계에서는 LLM이 filter_rows + sort_rows를 순차로 호출하면 됨 →
    #  Phase 3에서 제거 후보. 일단 호환을 위해 유지)
    {
        "type": "function",
        "function": {
            "name": "filter_then_sort",
            "description": (
                "필터 + 정렬을 한 도구로. 단순 케이스에 사용 (복합 의도는 "
                "filter_rows와 sort_rows를 순서대로 호출 권장)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_column":   {"type": "string"},
                    "filter_operator": {"type": "string", "enum": _OPERATORS},
                    "filter_value":    {},
                    "sort_column":     {"type": "string"},
                    "direction":       {"type": "string", "enum": _DIRECTIONS, "default": "asc"},
                    "use_last_result": {"type": "boolean", "default": False},
                },
                "required": ["filter_column", "filter_operator", "sort_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "head_aggregate",
            "description": "각 파일의 처음 n행만 추출해 수치 컬럼 합계. 예: '처음 5행 합계'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n":    {"type": "integer", "default": 5},
                    "func": {"type": "string", "enum": _AGG_FUNCS, "default": "sum"},
                },
            },
        },
    },
]


# ── 메타 정보 — 라우터·검증·UI가 활용 ─────────────────────────────────────────
TOOLS_BY_NAME: dict[str, dict] = {t["function"]["name"]: t for t in TOOL_SPECS}

# 체이닝 가능 도구 (use_last_result 노출됨)
CHAINABLE_TOOLS: set[str] = {
    "select_columns", "filter_rows", "sort_rows", "aggregate_data",
    "create_chart", "export_data", "filter_then_sort",
}

# 출력 타입별 분류 — 검증 단계에서 사용
TOOL_OUTPUT_TYPE: dict[str, str] = {
    "get_row_count":     "number",
    "analyze_missing":   "dataframe",
    "get_profile":       "dataframe",
    "select_columns":    "dataframe",
    "filter_rows":       "dataframe",
    "sort_rows":         "dataframe",
    "aggregate_data":    "dataframe",
    "merge_files":       "dataframe",
    "merge_same_format": "dataframe",
    "create_chart":      "plot",
    "export_data":       "dataframe",
    "filter_then_sort":  "dataframe",
    "head_aggregate":    "dataframe",
}


def get_specs_for_llm(provider: str = "openai") -> list[dict]:
    """프로바이더별 형식으로 spec 반환.

    openai/ollama: 기본 형식 그대로
    anthropic:     {function: {...}} → {name, description, input_schema}
    gemini:        FunctionDeclaration 구조로 변환 (별도 어댑터)
    """
    if provider in ("openai", "ollama"):
        return TOOL_SPECS

    if provider == "anthropic":
        return [
            {
                "name":        t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in TOOL_SPECS
        ]

    # Gemini는 별도 어댑터 필요 (FunctionDeclaration 객체 생성)
    raise NotImplementedError(f"provider={provider} 어댑터 미구현")
