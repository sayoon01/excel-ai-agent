"""used_range 기능 검증 — 실제 업로드 파일 기준.

실행: source venv/bin/activate && python test/test_used_range.py
"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (어디서 실행해도 동작)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.data.excel_processor import get_used_range, format_used_range

# ── 검증 기준값 (실측치) ──────────────────────────────────────────────────────
CASES = [
    {
        "file": ROOT / "uploads/4예실대비표.xlsx",
        "expected": {
            "first_row": 1, "last_row": 33,
            "first_col": 1, "last_col": 18,
            "data_rows": 33, "data_cols": 18,
            "filled_cells": 544, "total_cells": 594,
        },
    },
    {
        "file": ROOT / "uploads/5예실대비표.xlsx",
        "expected": {
            "first_row": 1, "last_row": 40,
            "first_col": 1, "last_col": 18,
            "data_rows": 40, "data_cols": 18,
            "filled_cells": 663, "total_cells": 720,
        },
    },
    {
        "file": ROOT / "uploads/7예실대비표.xlsx",
        "expected": {
            "first_row": 1, "last_row": 26,
            "first_col": 1, "last_col": 18,
            "data_rows": 26, "data_cols": 18,
            "filled_cells": 425, "total_cells": 468,
        },
    },
]

# ── 실행 ──────────────────────────────────────────────────────────────────────
all_passed = True

for case in CASES:
    path = Path(case["file"])
    exp = case["expected"]

    print(f"\n{'='*55}")
    print(f"파일: {path.name}")

    if not path.exists():
        print(f"  ❌ 파일 없음: {path}")
        all_passed = False
        continue

    ur = get_used_range(path)
    if ur is None:
        print("  ❌ 탐지 실패")
        all_passed = False
        continue

    print(f"  시트명     : {ur.sheet_name}")
    print(f"  범위       : {ur.first_row}~{ur.last_row}행 / {ur.first_col}~{ur.last_col}열")
    print(f"  데이터     : {ur.data_rows}행 × {ur.data_cols}열")
    print(f"  채워진 셀  : {ur.filled_cells} / {ur.total_cells}")
    print(f"  밀도       : {ur.density * 100:.1f}%")
    print(f"  요약       : {format_used_range(ur)}")

    checks = {
        "first_row":    ur.first_row,
        "last_row":     ur.last_row,
        "first_col":    ur.first_col,
        "last_col":     ur.last_col,
        "data_rows":    ur.data_rows,
        "data_cols":    ur.data_cols,
        "filled_cells": ur.filled_cells,
        "total_cells":  ur.total_cells,
    }

    file_ok = True
    for field, actual in checks.items():
        expected_val = exp[field]
        if actual != expected_val:
            print(f"  ❌ {field}: 기대={expected_val}, 실제={actual}")
            file_ok = False
            all_passed = False

    # 공통 품질 기준
    if ur.density < 0.80:
        print(f"  ⚠ 밀도 낮음: {ur.density * 100:.1f}% (기준 80% 이상)")

    if file_ok:
        print("  ✓ 모든 검증 통과")

print(f"\n{'='*55}")
print("전체 결과:", "✓ 모두 통과" if all_passed else "❌ 일부 실패")
