"""파일 정보 조회 도구 — tool 모드에서 직접 호출되는 함수들."""
from __future__ import annotations

import pandas as pd

from services.file_manager import read_file


# ── 공통 ──────────────────────────────────────────────────────────────────────

def _load_df(files_info: list[dict], file_idx: int = 0) -> pd.DataFrame | None:
    """files_info 리스트에서 지정 인덱스 파일을 DataFrame으로 로드."""
    if not files_info:
        return None
    entry = files_info[file_idx] if file_idx < len(files_info) else files_info[0]
    name = entry.get("name", "")
    sheet = entry.get("sheet")
    return read_file(name, sheet_name=sheet)


# ── Tool 함수들 ───────────────────────────────────────────────────────────────

def get_row_count(files_info: list[dict], **kwargs) -> dict:
    """행 수 반환.

    Returns:
        {"type": "number", "value": int, "label": str}
    """
    df = _load_df(files_info)
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}
    fname = files_info[0].get("name", "파일") if files_info else "파일"
    return {
        "type": "number",
        "value": len(df),
        "label": f"{fname} 행 수",
    }


def analyze_missing(files_info: list[dict], **kwargs) -> dict:
    """결측치 분석 — 컬럼별 결측 수·비율 DataFrame 반환.

    Returns:
        {"type": "dataframe", "value": pd.DataFrame, "label": str}
    """
    df = _load_df(files_info)
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    missing_count = df.isnull().sum()
    missing_pct = (missing_count / len(df) * 100).round(2)

    result = pd.DataFrame({
        "컬럼":     missing_count.index,
        "결측 수":  missing_count.values,
        "결측률(%)": missing_pct.values,
        "데이터 수": (len(df) - missing_count).values,
    })
    result = result.sort_values("결측 수", ascending=False).reset_index(drop=True)
    return {
        "type": "dataframe",
        "value": result,
        "label": "결측치 분석",
        "summary": (
            f"총 {len(df):,}행, {len(df.columns)}컬럼 — "
            f"결측치 있는 컬럼: {int((missing_count > 0).sum())}개"
        ),
    }


def get_profile(files_info: list[dict], **kwargs) -> dict:
    """컬럼 프로파일 — 타입·유니크·결측 요약 DataFrame 반환.

    Returns:
        {"type": "dataframe", "value": pd.DataFrame, "label": str}
    """
    df = _load_df(files_info)
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    rows = []
    for col in df.columns:
        s = df[col]
        dtype = str(s.dtype)
        is_numeric = pd.api.types.is_numeric_dtype(s)
        rows.append({
            "컬럼":    col,
            "타입":    dtype,
            "비어있지 않은 수": int(s.count()),
            "결측 수": int(s.isnull().sum()),
            "고유값 수": int(s.nunique()),
            "최솟값": float(s.min()) if is_numeric else str(s.dropna().min())[:20] if s.count() > 0 else "",
            "최댓값": float(s.max()) if is_numeric else str(s.dropna().max())[:20] if s.count() > 0 else "",
        })

    result = pd.DataFrame(rows)
    return {
        "type": "dataframe",
        "value": result,
        "label": f"컬럼 프로파일 ({len(df.columns)}개 컬럼)",
        "summary": f"{len(df):,}행 × {len(df.columns)}컬럼",
    }
