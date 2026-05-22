"""File upload, listing, preview, and deletion utilities."""
from pathlib import Path

import pandas as pd

from core.excel_processor import format_used_range, get_used_range, read_excel_smart
from core.quality_rules import profile_quality

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
RESULT_DIR = BASE_DIR / "results"

UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def save_uploaded(uploaded_file) -> Path:
    dest = UPLOAD_DIR / uploaded_file.name
    dest.write_bytes(uploaded_file.getbuffer())
    return dest


def list_files() -> list[str]:
    return sorted(
        f.name for f in UPLOAD_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    )


def delete_file(name: str) -> bool:
    path = UPLOAD_DIR / name
    if path.exists() and path.parent.resolve() == UPLOAD_DIR.resolve():
        path.unlink()
        return True
    return False


def read_file(name: str, sheet_name: str | None = None) -> pd.DataFrame | None:
    path = UPLOAD_DIR / name
    if not path.exists():
        return None
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return read_excel_smart(path, sheet_name=sheet_name)


def preview_file(name: str, nrows: int = 10, sheet_name: str | None = None) -> pd.DataFrame | None:
    """read_file과 동일한 스마트 읽기 후 상위 nrows 행 반환."""
    df = read_file(name, sheet_name=sheet_name)
    if df is None:
        return None
    df = df.head(nrows)
    # Streamlit Arrow 직렬화 호환: Int64/object 컬럼을 안전하게 변환
    for col in df.columns:
        if pd.api.types.is_extension_array_dtype(df[col]):
            df[col] = df[col].astype(object)
        elif df[col].dtype == object:
            df[col] = df[col].astype(str)
    return df


def get_file_info(name: str) -> dict | None:
    path = UPLOAD_DIR / name
    if not path.exists():
        return None
    size = path.stat().st_size
    df = read_file(name)
    if df is None:
        return None

    # 멀티 시트 감지 (xlsx만)
    sheet_names: list[str] = []
    if path.suffix.lower() in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True)
            sheet_names = wb.sheetnames
            wb.close()
        except Exception:
            pass

    # 결측치 컬럼만 추출 (0인 것 제외)
    null_counts: dict[str, int] = {
        col: int(cnt)
        for col, cnt in df.isnull().sum().items()
        if cnt > 0
    }

    ur = get_used_range(path)
    return {
        "name": name,
        "rows": len(df),
        "columns": len(df.columns),
        "size_kb": round(size / 1024, 1),
        "col_names": list(df.columns.astype(str)),
        "null_counts": null_counts,
        "dtypes": df.dtypes.astype(str).to_dict(),
        "sheet_names": sheet_names,
        "sheet_count": len(sheet_names),
        "used_range": format_used_range(ur) if ur else None,
        "used_range_raw": ur,
    }


def list_results() -> list[str]:
    return sorted(
        f.name for f in RESULT_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    )


def delete_result(name: str) -> bool:
    path = RESULT_DIR / name
    if path.exists() and path.parent.resolve() == RESULT_DIR.resolve():
        path.unlink()
        return True
    return False


def collect_files_info(file_names: list[str] | None = None) -> list[dict]:
    """파일 목록의 메타데이터(컬럼 타입, 결측치, 통계 등)를 수집한다."""
    names = file_names if file_names is not None else list_files()
    result = []
    for fname in names:
        df = read_file(fname)
        if df is None:
            continue

        mixed_type_cols = []
        for col in df.select_dtypes(include=["object", "string"]).columns:
            sample = df[col].dropna().head(100)
            if len(sample) > 0:
                ratio = pd.to_numeric(sample, errors="coerce").notna().mean()
                if ratio >= 0.7:
                    mixed_type_cols.append(str(col))

        head_sample = []
        for _, row in df.head(2).iterrows():
            head_sample.append({
                str(k): (str(v)[:30] if pd.notna(v) else None)
                for k, v in row.items()
            })

        numeric_stats: dict[str, dict] = {}
        for col in df.select_dtypes(include="number").columns:
            s = df[col].dropna()
            if len(s) > 0:
                numeric_stats[str(col)] = {
                    "min":  round(float(s.min()),  2),
                    "mean": round(float(s.mean()), 2),
                    "max":  round(float(s.max()),  2),
                }

        string_stats: dict[str, dict] = {}
        for col in df.select_dtypes(include=["object", "string"]).columns:
            if str(col) in mixed_type_cols:
                continue
            vc = df[col].dropna().value_counts()
            if len(vc) > 0:
                string_stats[str(col)] = {
                    "unique": int(df[col].nunique()),
                    "top": [str(v) for v in vc.index[:3].tolist()],
                }

        result.append({
            "name": fname,
            "rows": len(df),
            "columns": len(df.columns),
            "col_names": list(df.columns.astype(str)),
            "null_counts": df.isnull().sum().to_dict(),
            "dtypes": df.dtypes.astype(str).to_dict(),
            "mixed_type_cols": mixed_type_cols,
            "head_sample": head_sample,
            "numeric_stats": numeric_stats,
            "string_stats": string_stats,
            "quality_profile": profile_quality(df),
        })
    return result


