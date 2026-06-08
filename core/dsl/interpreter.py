"""DSL 인터프리터 — pipeline을 step 순서대로 실행.

각 op은 직접 pandas 호출. 자연어 파싱 없음.
LLM이 정확한 인자를 주면 결정적으로 동작.

반환 형식 (기존 dispatch_tool과 호환):
    {"type": "dataframe"|"plot"|"saved_file"|"error",
     "value": ...,
     "label": str,
     "summary": str,
     "log": [...]   # 각 step 실행 결과
    }
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pandas as pd

from core.dsl.spec import OPS, validate_pipeline, PipelineError
from services.file_manager import read_file


# ── 단일 op 구현 ─────────────────────────────────────────────────────────────

def _op_load(df, step, ctx):
    files_info = ctx.get("files_info", [])
    target_names = step.get("files")
    sheet        = step.get("sheet")
    concat       = step.get("concat", False)

    if target_names:
        entries = [e for e in files_info if e.get("name") in target_names]
    else:
        entries = files_info

    if not entries:
        raise RuntimeError("load: 지정한 파일을 찾을 수 없음")

    dfs = []
    for entry in entries:
        loaded = read_file(entry.get("name", ""), sheet_name=sheet or entry.get("sheet"))
        if loaded is not None and not loaded.empty:
            dfs.append(loaded)

    if not dfs:
        raise RuntimeError("load: 모든 파일 로드 실패")

    if concat and len(dfs) > 1:
        common = [c for c in dfs[0].columns if all(c in d.columns for d in dfs[1:])]
        return pd.concat([d[common] for d in dfs], ignore_index=True)
    return dfs[0] if len(dfs) == 1 else pd.concat(dfs, ignore_index=True, sort=False)


def _op_filter(df, step, ctx):
    col = step["column"]
    op  = step["operator"]
    val = step.get("value")

    if col not in df.columns:
        raise RuntimeError(f"filter: 컬럼 '{col}' 없음 (가능: {list(df.columns)[:5]}...)")

    s = df[col]
    if op == "gte":          mask = s >= val
    elif op == "lte":        mask = s <= val
    elif op == "gt":         mask = s > val
    elif op == "lt":         mask = s < val
    elif op == "eq":         mask = s == val
    elif op == "neq":        mask = s != val
    elif op == "contains":
        mask = s.astype(str).str.contains(str(val), na=False, regex=False)
    elif op == "not_contains":
        mask = ~s.astype(str).str.contains(str(val), na=False, regex=False)
    elif op == "isna":       mask = s.isna()
    elif op == "notna":      mask = s.notna()
    elif op == "in_range":
        vmax = step.get("value_max")
        if vmax is None:
            raise RuntimeError("filter: in_range에는 value_max 필요")
        mask = (s >= val) & (s <= vmax)
    elif op == "top_n":
        n = int(step.get("n", 10))
        return df.nlargest(n, col).reset_index(drop=True)
    elif op == "bottom_n":
        n = int(step.get("n", 10))
        return df.nsmallest(n, col).reset_index(drop=True)
    elif op in ("col_gt", "col_lt", "col_eq"):
        cmp_col = step.get("compare_column")
        if not cmp_col or cmp_col not in df.columns:
            raise RuntimeError(f"filter: compare_column '{cmp_col}' 없음")
        if op == "col_gt":   mask = df[col] >  df[cmp_col]
        elif op == "col_lt": mask = df[col] <  df[cmp_col]
        else:                mask = df[col] == df[cmp_col]
    else:
        raise RuntimeError(f"filter: 알 수 없는 operator '{op}'")

    return df[mask].reset_index(drop=True)


def _op_sort(df, step, ctx):
    col = step["column"]
    direction = step.get("direction", "asc")
    if col not in df.columns:
        raise RuntimeError(f"sort: 컬럼 '{col}' 없음")
    return df.sort_values(col, ascending=(direction == "asc")).reset_index(drop=True)


def _op_select(df, step, ctx):
    cols = step["columns"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"select: 컬럼 없음: {missing}")
    return df[cols].copy().reset_index(drop=True)


def _normalize_metrics(step: dict, df) -> list[tuple[str, str]]:
    """aggregate의 두 인자 형식을 [(column, func)] 리스트로 통일.

    우선순위:
    1. metrics 명시 → 그대로 사용
    2. value_columns + func → 변환
    3. 둘 다 없음 → 모든 수치 컬럼 × func
    """
    group_by = step.get("group_by")
    metrics = step.get("metrics")
    if metrics and isinstance(metrics, list):
        out = []
        for m in metrics:
            col = m.get("column")
            fn  = m.get("func") or m.get("agg") or "sum"  # agg 별칭도 허용
            if col:
                out.append((col, fn))
        if out:
            return out

    func = step.get("func", "sum")
    value_columns = step.get("value_columns")
    if not value_columns:
        value_columns = [c for c in df.columns
                         if pd.api.types.is_numeric_dtype(df[c]) and c != group_by]
    return [(c, func) for c in value_columns]


def _op_aggregate(df, step, ctx):
    """집계. metrics=[{column, func}] 형식과 value_columns+func 형식 둘 다 지원.

    결과 컬럼: group_by 컬럼은 이름 유지, value는 '{원본}_{func}' 형식.
    같은 컬럼에 여러 func 적용 시 각각 별도 컬럼.
    예: metrics=[{당년도집행,mean},{당년도집행,sum},{계획예산,sum}]
        → [비목, 당년도집행_mean, 당년도집행_sum, 계획예산_sum]
    """
    group_by = step.get("group_by")
    pairs = _normalize_metrics(step, df)
    if not pairs:
        raise RuntimeError("aggregate: 집계할 컬럼이 없음")

    # 컬럼 존재 검증
    missing = [c for c, _ in pairs if c not in df.columns]
    if missing:
        raise RuntimeError(f"aggregate: 컬럼 없음: {missing}")
    if group_by and group_by not in df.columns:
        raise RuntimeError(f"aggregate: group_by 컬럼 '{group_by}' 없음")

    # pandas .agg(dict) 호출 형식으로 변환 — 컬럼당 여러 func은 list로
    from collections import defaultdict
    by_col: dict[str, list[str]] = defaultdict(list)
    for col, fn in pairs:
        if fn not in by_col[col]:
            by_col[col].append(fn)
    agg_dict = {c: fs[0] if len(fs) == 1 else fs for c, fs in by_col.items()}

    if group_by:
        grouped = df.groupby(group_by).agg(agg_dict)
    else:
        # 전체 집계 — agg(dict) 결과를 1행 dataframe으로
        ser = df.agg(agg_dict)
        if isinstance(ser, pd.DataFrame):
            grouped = ser
        else:
            grouped = ser.to_frame().T

    # MultiIndex 컬럼이면 (col, func) → "col_func"으로 flatten
    if isinstance(grouped.columns, pd.MultiIndex):
        grouped.columns = [f"{a}_{b}" for a, b in grouped.columns]
    else:
        # 단일 func 케이스 — 모든 컬럼에 _func 붙임
        rename_map = {}
        for col, fs in by_col.items():
            if len(fs) == 1 and col in grouped.columns:
                rename_map[col] = f"{col}_{fs[0]}"
        grouped = grouped.rename(columns=rename_map)

    if group_by:
        result = grouped.reset_index()
    else:
        result = grouped.reset_index(drop=True)
    return result


def _op_chart(df, step, ctx):
    """차트 — 기존 chart_tools의 헬퍼를 재활용해 figure 생성 후 저장."""
    from core.tools.chart_tools import (
        _bar_chart, _line_chart, _pie_chart, _scatter_chart,
        _histogram_chart, _boxplot_chart, _save_fig,
    )

    chart_type = step.get("chart_type", "bar")
    x_col = step.get("x_column")
    y_cols = step.get("y_columns") or [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and c != x_col
    ][:3]
    title = step.get("title") or f"{x_col or ''} × {', '.join(y_cols[:2])}"

    if chart_type == "bar":
        fig = _bar_chart(df, x_col or df.columns[0], y_cols, title)
    elif chart_type == "line":
        fig = _line_chart(df, x_col or df.columns[0], y_cols, title)
    elif chart_type == "pie":
        fig = _pie_chart(df, x_col or df.columns[0], y_cols[0], title)
    elif chart_type == "scatter":
        if len(y_cols) < 2:
            raise RuntimeError("scatter: y_columns에 수치 2개 필요")
        fig = _scatter_chart(df, y_cols[0], y_cols[1], title)
    elif chart_type == "histogram":
        fig = _histogram_chart(df, y_cols[0], title)
    elif chart_type == "boxplot":
        fig = _boxplot_chart(df, y_cols[:4], x_col, title)
    else:
        raise RuntimeError(f"chart: 알 수 없는 type '{chart_type}'")

    path = _save_fig(fig, chart_type, title)
    return path


def _op_save(df, step, ctx):
    from services.file_manager import RESULT_DIR

    fmt = step.get("format", "xlsx")
    fname = step.get("filename")
    if not fname:
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"dsl_result_{ts}.{fmt}"
    if not fname.endswith(f".{fmt}"):
        fname = f"{fname}.{fmt}"

    dest = Path(RESULT_DIR) / fname
    if fmt == "csv":
        df.to_csv(dest, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(dest, index=False)
    return str(dest)


def _resolve_operand(df, val):
    """operand가 컬럼명이면 Series 반환, 숫자면 그대로."""
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str) and val in df.columns:
        return df[val]
    raise RuntimeError(f"calculate: operand '{val}'을 컬럼 또는 숫자로 해석 불가")


def _op_calculate(df, step, ctx):
    """파생 컬럼 생성. df에 새 컬럼 추가 후 반환."""
    left = _resolve_operand(df, step["left"])
    right = _resolve_operand(df, step["right"])
    op = step["operator"]
    name = step["name"]

    if op == "add":          result = left + right
    elif op == "subtract":   result = left - right
    elif op == "multiply":   result = left * right
    elif op == "divide":
        # 0 나눗셈 방지
        import numpy as np
        right_safe = right.replace(0, np.nan) if hasattr(right, "replace") else (
            np.nan if right == 0 else right
        )
        result = left / right_safe
    elif op == "abs_diff":   result = (left - right).abs() if hasattr(left, "abs") else abs(left - right)
    elif op == "percent":
        import numpy as np
        right_safe = right.replace(0, np.nan) if hasattr(right, "replace") else (
            np.nan if right == 0 else right
        )
        result = (left / right_safe) * 100
    else:
        raise RuntimeError(f"calculate: 알 수 없는 operator '{op}'")

    out = df.copy()
    out[name] = result
    return out


_OP_FNS = {
    "load":      _op_load,
    "filter":    _op_filter,
    "sort":      _op_sort,
    "select":    _op_select,
    "aggregate": _op_aggregate,
    "calculate": _op_calculate,
    "chart":     _op_chart,
    "save":      _op_save,
}


# ── 메인 진입점 ──────────────────────────────────────────────────────────────

def run_pipeline(pipeline: list[dict],
                 files_info: list[dict] | None = None,
                 llm_client=None) -> dict:
    """pipeline을 순차 실행. dispatch_tool과 호환되는 dict 반환.

    Returns:
        {"type": "dataframe"|"plot"|"saved_file"|"error",
         "value": ..., "label": str, "summary": str, "log": [...]}
    """
    try:
        validate_pipeline(pipeline)
    except PipelineError as e:
        return {"type": "error", "message": f"pipeline 검증 실패: {e}"}

    ctx = {"files_info": files_info or [], "llm_client": llm_client}
    log: list[dict] = []
    df = None

    for i, step in enumerate(pipeline):
        op_name = step["op"]
        fn = _OP_FNS.get(op_name)
        if fn is None:
            return {"type": "error", "message": f"step #{i}: 미구현 op '{op_name}'"}

        try:
            df = fn(df, step, ctx)
        except Exception as exc:
            log.append({"step": i, "op": op_name, "error": str(exc)})
            return {
                "type": "error",
                "message": f"step #{i} ({op_name}) 실행 실패: {exc}",
                "log": log,
            }

        log.append({
            "step": i, "op": op_name,
            "shape": (df.shape if isinstance(df, pd.DataFrame) else None),
            "result_type": OPS[op_name]["output"],
        })

    # 최종 출력 타입에 따른 반환
    final_out = OPS[pipeline[-1]["op"]]["output"]
    if final_out == "dataframe":
        return {
            "type": "dataframe",
            "value": df,
            "label": "DSL 결과",
            "summary": _summarize_log(log, df),
            "log": log,
        }
    if final_out == "plot":
        return {
            "type": "plot",
            "value": df,  # path
            "label": "DSL 차트",
            "summary": _summarize_log(log),
            "log": log,
        }
    if final_out == "saved_file":
        fname = Path(str(df)).name
        return {
            "type": "dataframe",
            "value": None,
            "label": "저장 완료",
            "summary": f"파일 저장: {fname}",
            "saved_files": [fname],
            "log": log,
        }
    return {"type": "error", "message": f"알 수 없는 최종 출력 타입: {final_out}"}


def _summarize_log(log: list[dict], final_df=None) -> str:
    ops = " → ".join(f"{e['op']}" + (f"{e['shape']}" if e.get("shape") else "")
                     for e in log)
    if isinstance(final_df, pd.DataFrame):
        return f"{ops}  (최종 {len(final_df)}행 × {len(final_df.columns)}컬럼)"
    return ops
