"""차트 생성 도구."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core.tools.font_setup import setup_korean_font
from services.file_manager import RESULT_DIR, read_file
from services.result_naming import chart_filename

setup_korean_font()


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


def _save_fig(fig: plt.Figure, chart_type: str, title: str, prompt: str = "") -> str:
    name = chart_filename(chart_type, title, prompt=prompt)
    path = RESULT_DIR / name
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


def _infer_scatter_cols(
    df: pd.DataFrame, prompt: str
) -> tuple[str | None, str | None]:
    """산점도용 x·y 수치 컬럼 두 개 추론."""
    prompt_lower = prompt.lower()
    num_cols = _pick_numeric_cols(df)
    hit = [c for c in num_cols if str(c).lower() in prompt_lower]
    if len(hit) >= 2:
        return hit[0], hit[1]
    if len(hit) == 1 and len(num_cols) >= 2:
        other = [c for c in num_cols if c != hit[0]]
        return hit[0], other[0]
    if len(num_cols) >= 2:
        return num_cols[0], num_cols[1]
    return None, None


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


def _scatter_chart(
    df: pd.DataFrame, x_col: str, y_col: str, title: str
) -> plt.Figure:
    """산점도 + 추세선."""
    import numpy as np
    data = df[[x_col, y_col]].dropna()
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(data[x_col], data[y_col], alpha=0.6, color=_PALETTE[0],
               edgecolors="white", s=60)
    if len(data) >= 3:
        z = np.polyfit(data[x_col], data[y_col], 1)
        xs = [data[x_col].min(), data[x_col].max()]
        ax.plot(xs, np.poly1d(z)(xs), "--", color=_PALETTE[1],
                alpha=0.8, linewidth=1.5, label="추세선")
        ax.legend(fontsize=10)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(title, fontsize=14, pad=12)
    fig.tight_layout()
    return fig


def _histogram_chart(df: pd.DataFrame, col: str, title: str) -> plt.Figure:
    """단일 컬럼 히스토그램."""
    data = df[col].dropna()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(data, bins="auto", color=_PALETTE[0], edgecolor="white", alpha=0.85)
    ax.set_xlabel(col)
    ax.set_ylabel("빈도")
    ax.set_title(title, fontsize=14, pad=12)
    fig.tight_layout()
    return fig


def _boxplot_chart(
    df: pd.DataFrame, y_cols: list[str], group_col: str | None, title: str
) -> plt.Figure:
    """박스플롯 — 그룹 컬럼이 있으면 그룹별, 없으면 컬럼별."""
    fig, ax = plt.subplots(figsize=(max(8, len(y_cols) * 2 + 2), 5))
    bp_kw = dict(
        patch_artist=True,
        medianprops=dict(color="black", linewidth=2),
    )

    if group_col and df[group_col].nunique() <= 12:
        groups = df[group_col].dropna().unique()
        data = [df.loc[df[group_col] == g, y_cols[0]].dropna().tolist() for g in groups]
        bp = ax.boxplot(data, labels=[str(g) for g in groups], **bp_kw)
        ax.set_xlabel(group_col)
        ax.tick_params(axis="x", rotation=20)
    else:
        data = [df[c].dropna().tolist() for c in y_cols]
        bp = ax.boxplot(data, labels=y_cols, **bp_kw)
        ax.tick_params(axis="x", rotation=20)

    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(_PALETTE[i % len(_PALETTE)])
        patch.set_alpha(0.6)

    ax.set_title(title, fontsize=14, pad=12)
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
    elif any(k in p for k in ["산점도", "scatter", "상관관계", "상관"]):
        chart_type = "scatter"
    elif any(k in p for k in ["히스토그램", "histogram", "분포도", "빈도분포"]):
        chart_type = "histogram"
    elif any(k in p for k in ["박스플롯", "박스", "boxplot", "box plot", "사분위", "분위수"]):
        chart_type = "boxplot"
    else:
        chart_type = "bar"

    try:
        if chart_type == "scatter":
            x_num, y_num = _infer_scatter_cols(df, prompt)
            if x_num is None or y_num is None:
                return {"type": "error", "message": "산점도에 사용할 수치형 컬럼이 2개 이상 필요합니다."}
            title = f"{x_num} vs {y_num}"
            fig = _scatter_chart(df, x_num, y_num, title)
            label = f"SCATTER 차트 — {title}"
            summary = f"{x_num}·{y_num} 산점도 생성 완료"

        elif chart_type == "histogram":
            cat_col, y_cols = _infer_chart_cols(df, prompt)
            if not y_cols:
                return {"type": "error", "message": "수치형 컬럼을 찾을 수 없습니다."}
            col = y_cols[0]
            title = f"{col} 분포"
            fig = _histogram_chart(df, col, title)
            label = f"HISTOGRAM — {title}"
            summary = f"{col} 히스토그램 생성 완료"

        elif chart_type == "boxplot":
            cat_col, y_cols = _infer_chart_cols(df, prompt)
            if not y_cols:
                return {"type": "error", "message": "수치형 컬럼을 찾을 수 없습니다."}
            title = "·".join(y_cols[:3]) + " 박스플롯"
            fig = _boxplot_chart(df, y_cols[:4], cat_col, title)
            label = f"BOXPLOT — {title}"
            summary = f"{'·'.join(y_cols[:3])} 박스플롯 생성 완료"

        else:
            cat_col, y_cols = _infer_chart_cols(df, prompt)
            if not y_cols:
                return {"type": "error", "message": "수치형 컬럼을 찾을 수 없습니다."}
            x_col  = cat_col or df.columns[0]
            y_disp = "·".join(y_cols) if len(y_cols) <= 3 else f"{y_cols[0]} 외 {len(y_cols)-1}개"
            title  = f"{x_col} × {y_disp}"

            if chart_type == "pie":
                fig = _pie_chart(df, x_col, y_cols[0], title)
            elif chart_type == "line":
                fig = _line_chart(df, x_col, y_cols, title)
            else:
                fig = _bar_chart(df, x_col, y_cols, title)

            series_info = f"{len(y_cols)}개 시리즈" if len(y_cols) > 1 else y_cols[0]
            label = f"{chart_type.upper()} 차트 — {title}"
            summary = f"{x_col} 기준 {series_info} {chart_type} 차트 생성 완료"

        path = _save_fig(fig, chart_type, title, prompt=prompt)
    except Exception as exc:
        return {"type": "error", "message": f"차트 생성 오류: {exc}"}

    fname = Path(path).name
    summary = f"{summary} → **{fname}**"

    return {
        "type": "plot",
        "value": path,
        "label": label,
        "summary": summary,
        "saved_files": [fname],
    }
