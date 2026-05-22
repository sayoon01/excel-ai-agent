"""차트 생성 도구."""
from __future__ import annotations

import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd

from services.file_manager import RESULT_DIR, read_file

# ── 한국어 폰트 설정 ──────────────────────────────────────────────────────────

def _setup_korean_font() -> None:
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareRoundB.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            prop = fm.FontProperties(fname=path)
            plt.rcParams["font.family"] = prop.get_name()
            plt.rcParams["axes.unicode_minus"] = False
            return
    plt.rcParams["axes.unicode_minus"] = False


_setup_korean_font()


# ── 공통 ──────────────────────────────────────────────────────────────────────

def _load_df(files_info: list[dict], file_idx: int = 0) -> pd.DataFrame | None:
    if not files_info:
        return None
    entry = files_info[file_idx] if file_idx < len(files_info) else files_info[0]
    return read_file(entry.get("name", ""), sheet_name=entry.get("sheet"))


def _pick_numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _pick_category_col(df: pd.DataFrame) -> str | None:
    """문자열(카테고리) 컬럼 중 첫 번째 반환."""
    for col in df.columns:
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            return col
    return None


def _save_fig(fig: plt.Figure) -> str:
    path = RESULT_DIR / f"chart_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _infer_chart_cols(
    df: pd.DataFrame, prompt: str
) -> tuple[str | None, list[str]]:
    """프롬프트 힌트로 x(카테고리)·y컬럼 목록 추론.

    Returns:
        (x_col, y_cols)  — y_cols는 1개 이상의 수치 컬럼 리스트
    """
    prompt_lower = prompt.lower()
    cat_col  = None
    num_cols_hit: list[str] = []

    for col in df.columns:
        cname = str(col).lower()
        if cname in prompt_lower:
            if pd.api.types.is_numeric_dtype(df[col]):
                num_cols_hit.append(col)
            else:
                cat_col = col

    if cat_col is None:
        cat_col = _pick_category_col(df)

    all_nums = _pick_numeric_cols(df)
    if not num_cols_hit:
        # 프롬프트에 수치 컬럼 힌트가 없으면 최대 4개까지 자동 선택
        num_cols_hit = all_nums[:4]

    return cat_col, num_cols_hit


_PALETTE = ["#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899"]


# ── 차트 생성 함수 ─────────────────────────────────────────────────────────────

def _bar_chart(
    df: pd.DataFrame, x_col: str, y_cols: list[str], title: str
) -> plt.Figure:
    """단일 또는 멀티 시리즈 막대 차트."""
    import numpy as np

    top = df.nlargest(15, y_cols[0]) if len(df) > 15 else df
    x_labels = top[x_col].astype(str).tolist()
    n_series = len(y_cols)
    x_pos    = np.arange(len(x_labels))
    width    = 0.8 / n_series

    fig, ax = plt.subplots(figsize=(max(10, len(x_labels) * 0.6), 5))
    for i, ycol in enumerate(y_cols):
        offset = (i - (n_series - 1) / 2) * width
        ax.bar(
            x_pos + offset, top[ycol],
            width=width * 0.9,
            color=_PALETTE[i % len(_PALETTE)],
            label=ycol,
            edgecolor="white",
        )
    ax.set_xticks(x_pos)
    ax.set_xticklabels(x_labels, rotation=30, ha="right")
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xlabel(x_col)
    if n_series > 1:
        ax.legend()
    fig.tight_layout()
    return fig


def _line_chart(
    df: pd.DataFrame, x_col: str, y_cols: list[str], title: str
) -> plt.Figure:
    """단일 또는 멀티 시리즈 선 차트."""
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, ycol in enumerate(y_cols):
        ax.plot(
            df[x_col].astype(str), df[ycol],
            marker="o", linewidth=2,
            color=_PALETTE[i % len(_PALETTE)],
            label=ycol,
        )
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xlabel(x_col)
    ax.tick_params(axis="x", rotation=30)
    if len(y_cols) > 1:
        ax.legend()
    fig.tight_layout()
    return fig


def _pie_chart(df: pd.DataFrame, label_col: str, value_col: str, title: str) -> plt.Figure:
    top = df.nlargest(8, value_col) if len(df) > 8 else df
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(
        top[value_col],
        labels=top[label_col].astype(str),
        autopct="%1.1f%%",
        startangle=90,
        colors=plt.cm.Set3.colors,  # type: ignore[attr-defined]
    )
    ax.set_title(title, fontsize=14, pad=12)
    fig.tight_layout()
    return fig


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def create_chart(files_info: list[dict], prompt: str = "", **kwargs) -> dict:
    """프롬프트에서 차트 종류·컬럼을 추론해 PNG로 저장 후 경로 반환.

    Returns:
        {"type": "plot", "value": str(path), "label": str, "summary": str}
    """
    df = _load_df(files_info)
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    cat_col, y_cols = _infer_chart_cols(df, prompt)
    if not y_cols:
        return {"type": "error", "message": "수치형 컬럼을 찾을 수 없습니다."}

    p = prompt.lower()
    if any(k in p for k in ["파이", "pie", "원형"]):
        chart_type = "pie"
    elif any(k in p for k in ["선", "line", "라인", "추이"]):
        chart_type = "line"
    else:
        chart_type = "bar"

    x_col  = cat_col or df.columns[0]
    y_disp = "·".join(y_cols) if len(y_cols) <= 3 else f"{y_cols[0]} 외 {len(y_cols)-1}개"
    title  = f"{x_col} × {y_disp}"

    try:
        if chart_type == "pie":
            # 파이 차트는 단일 y만 지원
            fig = _pie_chart(df, x_col, y_cols[0], title)
        elif chart_type == "line":
            fig = _line_chart(df, x_col, y_cols, title)
        else:
            fig = _bar_chart(df, x_col, y_cols, title)

        path = _save_fig(fig)
    except Exception as exc:
        return {"type": "error", "message": f"차트 생성 오류: {exc}"}

    series_info = f"{len(y_cols)}개 시리즈" if len(y_cols) > 1 else y_cols[0]
    return {
        "type": "plot",
        "value": path,
        "label": f"{chart_type.upper()} 차트 — {title}",
        "summary": f"{x_col} 기준 {series_info} {chart_type} 차트 생성 완료",
    }
