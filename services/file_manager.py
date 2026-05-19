"""File upload, listing, preview, and deletion utilities."""
from pathlib import Path

import pandas as pd

from core.excel_processor import format_used_range, get_used_range

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


def read_file(name: str) -> pd.DataFrame | None:
    path = UPLOAD_DIR / name
    if not path.exists():
        return None
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def preview_file(name: str, nrows: int = 10) -> pd.DataFrame | None:
    path = UPLOAD_DIR / name
    if not path.exists():
        return None
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, nrows=nrows)
    else:
        df = pd.read_excel(path, nrows=nrows)
    # 쉼표 포함 숫자 문자열 등 Arrow 변환 불가 컬럼을 str로 강제 변환
    for col in df.columns:
        if df[col].dtype == object:
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


def build_file_context(mode: str = "codegen") -> str:
    files = list_files()
    if not files:
        return ""

    if mode == "codegen":
        parts = ["## 업로드된 파일:\n"]
        for fname in files:
            df = read_file(fname)
            if df is None:
                continue
            parts.append(f'files["{fname}"]  # {len(df)}행 × {len(df.columns)}열')
            parts.append(f"  컬럼: {', '.join(df.columns.astype(str))}")
            parts.append(f"  타입: {dict(df.dtypes.astype(str))}")
            parts.append("  샘플 (처음 5행):")
            parts.append(df.head(5).to_string(index=False))
            parts.append("")
        return "\n".join(parts)

    parts = ["사용자가 다음 파일들을 업로드했습니다:\n"]
    for fname in files:
        df = read_file(fname)
        if df is None:
            continue
        parts.append(f"## 파일: {fname} ({len(df)}행 × {len(df.columns)}열)")
        parts.append(f"컬럼: {', '.join(df.columns.astype(str))}")
        parts.append(df.head(20).to_string(index=False))
        if len(df) > 20:
            parts.append(f"... ({len(df) - 20}개 행 더 있음)")
        parts.append("")
    return "\n".join(parts)
