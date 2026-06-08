"""DSL op 명세 — pipeline의 각 step이 만족해야 할 schema.

설계 원칙:
- op 인자명은 core/tools/tool_specs.py와 통일 (column/operator/value/func/direction)
- enum 값 영문 ASCII (asc/desc/gte/sum/...)
- 인자 검증은 validate_pipeline()이 담당 — 실행 전 오류 조기 발견
"""
from __future__ import annotations


# ── 공통 enum ────────────────────────────────────────────────────────────────
OPERATORS = [
    "gte", "lte", "gt", "lt", "eq", "neq",
    "contains", "not_contains", "isna", "notna",
    "in_range", "top_n", "bottom_n",
    "col_gt", "col_lt", "col_eq",
]
AGG_FUNCS    = ["sum", "mean", "max", "min", "count", "median", "std"]
DIRECTIONS   = ["asc", "desc"]
CHART_TYPES  = ["bar", "line", "pie", "scatter", "histogram", "boxplot"]
FILE_FORMATS = ["xlsx", "csv"]
CALC_OPS     = ["add", "subtract", "multiply", "divide", "abs_diff", "percent"]
# percent = (left / right) * 100,  abs_diff = |left - right|


# ── op 명세 ──────────────────────────────────────────────────────────────────
# 각 op는 입력 타입 / 출력 타입 / 인자 schema를 가진다.
#   input  = None        : 파이프라인 첫 step에서만 가능 (load)
#   input  = "dataframe" : 직전 step의 dataframe을 받음
#   output : 다음 step 또는 최종 사용자에게 전달되는 값의 타입
OPS: dict[str, dict] = {
    "load": {
        "description": "파일을 dataframe으로 로드. files 미지정 시 files_info 전체.",
        "input":  None,
        "output": "dataframe",
        "args": {
            "files":      {"type": "array",   "items": "string", "required": False},
            "sheet":      {"type": "string",  "required": False},
            "concat":     {"type": "boolean", "required": False, "default": False,
                           "description": "여러 파일을 세로로 concat 후 반환"},
        },
    },
    "filter": {
        "description": "조건에 맞는 행만 추출",
        "input":  "dataframe",
        "output": "dataframe",
        "args": {
            "column":         {"type": "string",  "required": True},
            "operator":       {"type": "string",  "enum": OPERATORS, "required": True},
            "value":          {"type": "any",     "required": False},
            "value_max":      {"type": "number",  "required": False},
            "compare_column": {"type": "string",  "required": False},
            "n":              {"type": "integer", "required": False},
        },
    },
    "sort": {
        "description": "지정 컬럼 기준 정렬",
        "input":  "dataframe",
        "output": "dataframe",
        "args": {
            "column":    {"type": "string", "required": True},
            "direction": {"type": "string", "enum": DIRECTIONS, "default": "asc"},
        },
    },
    "select": {
        "description": "지정 컬럼만 추출",
        "input":  "dataframe",
        "output": "dataframe",
        "args": {
            "columns": {"type": "array", "items": "string", "required": True},
        },
    },
    "aggregate": {
        "description": (
            "수치 컬럼 집계. 두 가지 인자 방식 지원:\n"
            "1. metrics=[{column, func}] — 컬럼마다 다른 func 가능 (권장)\n"
            "2. value_columns=[...] + func=... — 모든 컬럼에 같은 func (단순 케이스)\n"
            "group_by 있으면 그룹별, 없으면 전체"
        ),
        "input":  "dataframe",
        "output": "dataframe",
        "args": {
            "group_by":      {"type": "string", "required": False},
            "metrics":       {"type": "array", "items": "object", "required": False,
                              "description": "[{column, func}] 형식. 컬럼별 다른 func"},
            "value_columns": {"type": "array", "items": "string", "required": False,
                              "description": "단순 케이스용 (metrics와 둘 중 하나만 사용)"},
            "func":          {"type": "string", "enum": AGG_FUNCS, "default": "sum",
                              "description": "value_columns와 함께 사용"},
        },
    },
    "calculate": {
        "description": (
            "두 operand(컬럼 또는 숫자)로 새 파생 컬럼 생성. "
            "복잡한 식은 calculate를 여러 step으로 분해."
        ),
        "input":  "dataframe",
        "output": "dataframe",
        "args": {
            # left/right는 컬럼명(string) 또는 상수(number) 둘 다 허용
            "left":     {"type": "any", "required": True},
            "operator": {"type": "string", "enum": CALC_OPS, "required": True},
            "right":    {"type": "any", "required": True},
            "name":     {"type": "string", "required": True,
                         "description": "새 컬럼 이름"},
        },
    },
    "chart": {
        "description": "df를 차트로 변환",
        "input":  "dataframe",
        "output": "plot",
        "args": {
            "chart_type": {"type": "string", "enum": CHART_TYPES, "default": "bar"},
            "x_column":   {"type": "string", "required": False},
            "y_columns":  {"type": "array", "items": "string", "required": False},
            "title":      {"type": "string", "required": False},
        },
    },
    "save": {
        "description": "df를 파일로 저장",
        "input":  "dataframe",
        "output": "saved_file",
        "args": {
            "format":   {"type": "string", "enum": FILE_FORMATS, "default": "xlsx"},
            "filename": {"type": "string", "required": False},
        },
    },
}


# ── 검증 ─────────────────────────────────────────────────────────────────────
class PipelineError(ValueError):
    """잘못된 pipeline 정의 — 실행 전 발견"""


def validate_pipeline(pipeline: list[dict]) -> None:
    """pipeline의 구조와 op 흐름을 검증. 잘못된 경우 PipelineError raise."""
    if not isinstance(pipeline, list) or not pipeline:
        raise PipelineError("pipeline은 비어있지 않은 리스트여야 합니다")

    prev_output = None
    for i, step in enumerate(pipeline):
        if not isinstance(step, dict) or "op" not in step:
            raise PipelineError(f"step #{i}: dict + 'op' 키 필요")

        op_name = step["op"]
        if op_name not in OPS:
            raise PipelineError(f"step #{i}: 알 수 없는 op '{op_name}' "
                                f"(가능: {', '.join(OPS)})")

        spec = OPS[op_name]

        # 입력 타입 호환성
        if spec["input"] is None and i != 0:
            raise PipelineError(f"step #{i} ({op_name}): 첫 step에서만 사용 가능")
        if spec["input"] == "dataframe" and i == 0:
            raise PipelineError(f"step #{i} ({op_name}): 'load' 같은 dataframe 생성 op이 먼저 필요")
        if spec["input"] == "dataframe" and prev_output != "dataframe":
            raise PipelineError(f"step #{i} ({op_name}): 직전 출력이 dataframe이 아님")

        # 필수 인자 검증
        for arg_name, arg_spec in spec["args"].items():
            if arg_spec.get("required") and arg_name not in step:
                raise PipelineError(f"step #{i} ({op_name}): 필수 인자 '{arg_name}' 누락")

        # enum 값 검증
        for arg_name, arg_spec in spec["args"].items():
            if arg_name in step and "enum" in arg_spec:
                if step[arg_name] not in arg_spec["enum"]:
                    raise PipelineError(
                        f"step #{i} ({op_name}.{arg_name}): "
                        f"'{step[arg_name]}'은 enum에 없음 ({arg_spec['enum']})"
                    )

        prev_output = spec["output"]


def list_ops() -> list[str]:
    return list(OPS.keys())


# ── 데이터 인지 검증 ─────────────────────────────────────────────────────────

def _suggest_column(missing: str, available: list[str], n: int = 3) -> list[str]:
    """존재하지 않는 컬럼명에 대해 비슷한 것 n개 제안."""
    m = missing.lower()
    scored = []
    for c in available:
        c_low = str(c).lower()
        # 부분 포함 점수 + 길이 차이로 단순 랭킹
        if m in c_low or c_low in m:
            scored.append((0, c))
        elif any(seg in c_low for seg in m.split("_") if len(seg) > 1):
            scored.append((1, c))
    scored.sort()
    return [c for _, c in scored[:n]]


def validate_pipeline_with_data(
    pipeline: list[dict],
    files_info: list[dict],
) -> None:
    """schema 검증 + 데이터 존재 검증.

    환각 차단 항목:
    - 파일명이 files_info에 존재하는지
    - 모든 컬럼 인자가 현재 dataframe에 존재하는지 (step 순서 따라 추적)
    - n 인자는 1 이상

    컬럼 추적 정책:
    - load 후: 대상 파일들의 컬럼 합집합
    - aggregate 후: group_by + {col}_{func} (인터프리터 컨벤션과 동일)
    - select 후: 명시한 컬럼만
    - filter/sort 후: 변동 없음
    - chart/save 후: 검증 종료 (terminal)

    불확실한 경우(value_columns 미명시 등)는 검증을 skip → false positive 방지.
    """
    # 1) schema 먼저
    validate_pipeline(pipeline)

    # 2) 파일·컬럼 추적
    available_files = {fi.get("name") for fi in files_info}
    current_cols: set[str] | None = None  # None = 알 수 없음 (검증 skip)

    for i, step in enumerate(pipeline):
        op = step["op"]

        if op == "load":
            files = step.get("files")
            if files:
                missing = [f for f in files if f not in available_files]
                if missing:
                    raise PipelineError(
                        f"step #{i} (load): 존재하지 않는 파일: {missing}. "
                        f"사용 가능: {sorted(available_files)}"
                    )
                entries = [fi for fi in files_info if fi.get("name") in files]
            else:
                entries = files_info
            cols: set[str] = set()
            for fi in entries:
                names = fi.get("col_names") or fi.get("columns") or []
                cols.update(str(c) for c in names)
            current_cols = cols if cols else None

        elif op == "filter":
            if current_cols is None:
                continue
            _validate_col(step.get("column"), current_cols, i, "filter.column")
            if step.get("compare_column"):
                _validate_col(step["compare_column"], current_cols, i, "filter.compare_column")
            n = step.get("n")
            if n is not None and int(n) < 1:
                raise PipelineError(f"step #{i} (filter): n은 1 이상이어야 함 (현재: {n})")

        elif op == "sort":
            if current_cols is None:
                continue
            _validate_col(step.get("column"), current_cols, i, "sort.column")

        elif op == "select":
            if current_cols is None:
                continue
            cols_req = step.get("columns") or []
            missing = [c for c in cols_req if c not in current_cols]
            if missing:
                suggestions = {
                    c: _suggest_column(c, list(current_cols)) for c in missing
                }
                raise PipelineError(
                    f"step #{i} (select): 존재하지 않는 컬럼: {missing}. "
                    f"비슷한 컬럼: {suggestions}"
                )
            current_cols = set(cols_req)  # select 후엔 명시 컬럼만

        elif op == "aggregate":
            if current_cols is None:
                continue
            group_by = step.get("group_by")
            if group_by:
                _validate_col(group_by, current_cols, i, "aggregate.group_by")

            # 두 형식 모두 검증 후 컬럼 추적
            metrics = step.get("metrics")
            new_cols: set[str] = set()
            if group_by:
                new_cols.add(group_by)

            if metrics and isinstance(metrics, list):
                for j, m in enumerate(metrics):
                    col = m.get("column")
                    fn  = m.get("func") or m.get("agg") or "sum"
                    if not col:
                        raise PipelineError(
                            f"step #{i} (aggregate.metrics[{j}]): 'column' 필수"
                        )
                    _validate_col(col, current_cols, i, f"aggregate.metrics[{j}].column")
                    if fn not in AGG_FUNCS:
                        raise PipelineError(
                            f"step #{i} (aggregate.metrics[{j}].func): "
                            f"'{fn}'은 enum에 없음 ({AGG_FUNCS})"
                        )
                    new_cols.add(f"{col}_{fn}")
                current_cols = new_cols
            else:
                value_columns = step.get("value_columns") or []
                if value_columns:
                    missing = [c for c in value_columns if c not in current_cols]
                    if missing:
                        suggestions = {
                            c: _suggest_column(c, list(current_cols)) for c in missing
                        }
                        raise PipelineError(
                            f"step #{i} (aggregate.value_columns): 존재하지 않는 컬럼: {missing}. "
                            f"비슷한 컬럼: {suggestions}"
                        )
                func = step.get("func", "sum")
                if value_columns:
                    new_cols.update(f"{c}_{func}" for c in value_columns)
                    current_cols = new_cols
                else:
                    # value_columns 미명시 = 모든 numeric에 func 적용 → 정확 추적 불가
                    current_cols = None

        elif op == "calculate":
            if current_cols is None:
                continue
            # left/right가 컬럼명이면 존재 확인 (숫자면 skip)
            for arg_name in ("left", "right"):
                val = step.get(arg_name)
                if isinstance(val, str):  # 컬럼명
                    _validate_col(val, current_cols, i, f"calculate.{arg_name}")
            name = step.get("name")
            if not name or not isinstance(name, str):
                raise PipelineError(f"step #{i} (calculate): 'name' 필수")
            # 새 컬럼이 추가됨
            current_cols = set(current_cols) | {name}

        elif op == "chart":
            if current_cols is None:
                continue
            if step.get("x_column"):
                _validate_col(step["x_column"], current_cols, i, "chart.x_column")
            for c in (step.get("y_columns") or []):
                _validate_col(c, current_cols, i, "chart.y_columns")
            # chart는 terminal — 이후 step 없음 가정

        elif op == "save":
            pass  # 파일 저장은 컬럼 검증 불필요


def _validate_col(col, current_cols: set[str],
                  step_i: int, arg_label: str) -> None:
    if not col:
        return
    # LLM이 list를 단일 column 자리에 넣은 경우 — 친절한 에러
    if isinstance(col, (list, tuple)):
        raise PipelineError(
            f"step #{step_i} ({arg_label}): 단일 컬럼명이 와야 하는데 {col} (list) 가 옴. "
            f"여러 컬럼이 필요하면 다른 인자(예: columns)를 사용하라"
        )
    col = str(col)
    if col in current_cols:
        return
    suggestions = _suggest_column(col, list(current_cols))
    suggestion_msg = f" 비슷한 컬럼: {suggestions}" if suggestions else ""
    raise PipelineError(
        f"step #{step_i} ({arg_label}): 존재하지 않는 컬럼 '{col}'.{suggestion_msg}"
    )
