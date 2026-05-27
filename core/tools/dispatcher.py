"""Tool 이름 → 함수 디스패처 (캐시 포함)."""
from __future__ import annotations

from core.tools.chart_tools import create_chart
from core.tools.data_tools import (
    aggregate_data, export_data, filter_rows, filter_then_sort,
    head_aggregate, merge_files, merge_same_format, sort_rows,
)
from core.tools.file_tools import analyze_missing, get_profile, get_row_count
from core.tools.tool_cache import get as cache_get, put as cache_put

_REGISTRY: dict[str, callable] = {
    "get_row_count":    get_row_count,
    "analyze_missing":  analyze_missing,
    "get_profile":      get_profile,
    "aggregate_data":   aggregate_data,
    "filter_rows":      filter_rows,
    "filter_then_sort": filter_then_sort,
    "head_aggregate":   head_aggregate,
    "sort_rows":        sort_rows,
    "merge_files":        merge_files,
    "merge_same_format":  merge_same_format,
    "create_chart":       create_chart,
    "export_data":      export_data,
}

# 매번 새로 실행해야 하는 도구 (캐시 제외)
_NO_CACHE = {"export_data", "create_chart"}


def dispatch_tool(
    tool_name: str,
    files_info: list[dict],
    prompt: str = "",
    use_cache: bool = True,
    **extra,
) -> dict:
    """등록된 tool을 호출하고 결과 dict를 반환.

    use_cache=True(기본)면 동일 요청은 캐시에서 즉시 반환.
    export_data·create_chart는 항상 새로 실행.

    Returns:
        {"type": "dataframe"|"number"|"string"|"plot"|"error",
         "value": ..., "label": str, "cached": bool, ...}
    """
    fn = _REGISTRY.get(tool_name)
    if fn is None:
        return {"type": "error", "message": f"알 수 없는 도구: {tool_name}"}

    # llm_client / last_result는 캐시 가용성에 영향 없음 — 제외 후 판단
    _extra_for_cache = {k: v for k, v in extra.items()
                        if k not in ("llm_client", "last_result")}
    cacheable = use_cache and tool_name not in _NO_CACHE and not _extra_for_cache

    if cacheable:
        cached = cache_get(tool_name, files_info, prompt)
        if cached is not None:
            return {**cached, "cached": True}

    try:
        result = fn(files_info=files_info, prompt=prompt, **extra)
    except Exception as exc:
        return {"type": "error", "message": str(exc)}

    if cacheable and result.get("type") != "error":
        cache_put(tool_name, files_info, prompt, result)

    return {**result, "cached": False}
