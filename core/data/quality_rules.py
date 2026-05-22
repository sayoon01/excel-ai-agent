"""Generic data quality profiling rules for DataFrames."""
from __future__ import annotations

import re

import pandas as pd

_SUMMARY_RE = re.compile(
    # Korean
    r"소계|합계|총계|^계$|합 계|소 계"
    # Japanese
    r"|合計|小計|総計|合 計|小 計"
    # Chinese (Traditional & Simplified)
    r"|總計|總額|总计|总额|小計|合計"
    # English
    r"|total|subtotal|grand.total|sum.total|grand.sum"
    # German
    r"|gesamt|zwischensumme|gesamtsumme"
    # French / Spanish / Portuguese
    r"|sous.total|sous total|totale|totales|subtotal",
    re.IGNORECASE,
)


def profile_quality(df: pd.DataFrame) -> dict:
    """Compute a structured quality profile dict for a DataFrame.

    Returns
    -------
    missing        : {col: rate}  — cols with any missing values
    duplicates     : int          — fully duplicate row count
    summary_rows   : int          — rows containing 소계/합계 etc.
    numeric_outliers: {col: cnt}  — IQR×3 outliers per numeric col
    mixed_type     : [col]        — object cols with 30-70% numeric values
    const_cols     : [col]        — cols with only one distinct value
    total_rows     : int
    """
    n = len(df)
    if n == 0:
        return {"total_rows": 0}

    # 1. 결측률
    missing: dict[str, float] = {
        str(col): round(df[col].isna().sum() / n, 3)
        for col in df.columns
        if df[col].isna().sum() > 0
    }

    # 2. 완전 중복 행
    duplicates = int(df.duplicated().sum())

    # 3. 집계 행 감지
    summary_rows = 0
    for col in df.select_dtypes(include=["object"]).columns:
        hits = df[col].dropna().astype(str).str.contains(_SUMMARY_RE, regex=True)
        summary_rows = max(summary_rows, int(hits.sum()))

    # 4. 수치형 이상값 (IQR×3)
    numeric_outliers: dict[str, int] = {}
    for col in df.select_dtypes(include="number").columns:
        s = df[col].dropna()
        if len(s) < 4:
            continue
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        if iqr == 0:
            continue
        cnt = int(((s < q1 - 3 * iqr) | (s > q3 + 3 * iqr)).sum())
        if cnt > 0:
            numeric_outliers[str(col)] = cnt

    # 5. 타입 혼재 컬럼 (object인데 30-70%가 숫자)
    mixed_type: list[str] = []
    for col in df.select_dtypes(include=["object"]).columns:
        sample = df[col].dropna().head(200)
        if len(sample) < 4:
            continue
        ratio = pd.to_numeric(sample, errors="coerce").notna().mean()
        if 0.3 < ratio < 0.7:
            mixed_type.append(str(col))

    # 6. 상수 컬럼 (고유값 1개)
    const_cols: list[str] = [
        str(col) for col in df.columns
        if df[col].nunique(dropna=True) == 1 and df[col].notna().any()
    ]

    return {
        "missing": missing,
        "duplicates": duplicates,
        "summary_rows": summary_rows,
        "numeric_outliers": numeric_outliers,
        "mixed_type": mixed_type,
        "const_cols": const_cols,
        "total_rows": n,
    }


def bullets_from_profile(profile: dict) -> list[str]:
    """Convert a quality profile dict into human-readable diagnostic bullets."""
    if not profile or profile.get("total_rows", 0) == 0:
        return []

    bullets: list[str] = []

    # 결측률 > 20%인 컬럼
    high_missing = sorted(
        ((col, rate) for col, rate in profile.get("missing", {}).items() if rate > 0.2),
        key=lambda x: -x[1],
    )
    for col, rate in high_missing[:3]:
        bullets.append(f"{col} 컬럼 결측률 {rate * 100:.0f}%")

    # 중복 행
    dupes = profile.get("duplicates", 0)
    if dupes > 0:
        bullets.append(f"완전 중복 행 {dupes:,}개 포함")

    # 집계 행
    summary = profile.get("summary_rows", 0)
    if summary > 0:
        bullets.append(f"집계(합계·소계·total 등) 행 {summary}개 포함 가능성")

    # 이상값
    for col, cnt in list(profile.get("numeric_outliers", {}).items())[:2]:
        bullets.append(f"{col} 이상값 {cnt:,}개 탐지")

    # 타입 혼재
    mixed = profile.get("mixed_type", [])
    if mixed:
        cols_str = ", ".join(mixed[:2])
        suffix = f" 외 {len(mixed) - 2}개" if len(mixed) > 2 else ""
        bullets.append(f"숫자·문자 혼재 컬럼: {cols_str}{suffix}")

    # 상수 컬럼
    const = profile.get("const_cols", [])
    if const:
        cols_str = ", ".join(const[:2])
        suffix = f" 외 {len(const) - 2}개" if len(const) > 2 else ""
        bullets.append(f"단일 값만 존재하는 컬럼: {cols_str}{suffix}")

    return bullets
