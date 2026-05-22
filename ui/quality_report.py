"""파일 업로드 직후 자동 데이터 품질 리포트 (LLM 없이 코드로 직접 렌더링)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.file_manager import collect_files_info


@st.cache_data(show_spinner=False)
def load_files_info(file_names: tuple) -> list[dict]:
    """파일 목록이 바뀌지 않으면 캐시된 결과를 재사용."""
    return collect_files_info(list(file_names))


def render_compact_quality(fi: dict) -> None:
    """사이드바 파일 미리보기 하단 — 한두 줄 컴팩트 품질 요약."""
    # 결측치 TOP 3
    null_items = sorted(
        ((k, v) for k, v in fi["null_counts"].items() if v > 0),
        key=lambda x: -x[1],
    )[:3]
    if null_items:
        parts = "  ·  ".join(f"{k} ({v}개)" for k, v in null_items)
        st.caption(f"결측치  {parts}")

    # 문제 배지
    unnamed_cnt = sum(1 for c in fi["col_names"] if "unnamed" in c.lower())
    seen: dict[str, int] = {}
    for c in fi["col_names"]:
        seen[c] = seen.get(c, 0) + 1
    dup_cnt = sum(1 for v in seen.values() if v > 1)
    mixed_cnt = len(fi.get("mixed_type_cols", []))

    badges = []
    if unnamed_cnt:
        badges.append(
            f'<span style="background:#FEF3C7;color:#92400E;'
            f'padding:2px 8px;border-radius:10px;font-size:11px;">'
            f'Unnamed {unnamed_cnt}개</span>'
        )
    if dup_cnt:
        badges.append(
            f'<span style="background:#DBEAFE;color:#1E40AF;'
            f'padding:2px 8px;border-radius:10px;font-size:11px;">'
            f'중복 컬럼 {dup_cnt}개</span>'
        )
    if mixed_cnt:
        badges.append(
            f'<span style="background:#FCE7F3;color:#9D174D;'
            f'padding:2px 8px;border-radius:10px;font-size:11px;">'
            f'타입 불일치 {mixed_cnt}개</span>'
        )

    if badges:
        st.markdown("  ".join(badges), unsafe_allow_html=True)
    elif not null_items:
        st.caption("✓ 품질 문제 없음")


def render_quality_report(files_info: list[dict]) -> None:
    if not files_info:
        return

    st.markdown("#### 데이터 품질 리포트")

    for fi in files_info:
        with st.expander(f"📄 {fi['name']}", expanded=True):
            col_miss, col_issues, col_summary = st.columns([2, 1.5, 1])

            # ── 결측치 TOP 5 ──────────────────────────────────────────────
            with col_miss:
                st.caption("결측치 많은 컬럼")
                null_items = sorted(
                    ((k, v) for k, v in fi["null_counts"].items() if v > 0),
                    key=lambda x: -x[1],
                )[:5]
                if null_items:
                    null_df = pd.DataFrame(null_items, columns=["컬럼명", "결측수"])
                    null_df["결측율"] = (
                        (null_df["결측수"] / fi["rows"] * 100).round(1).astype(str) + "%"
                    )
                    st.dataframe(null_df, hide_index=True, use_container_width=True, height=210)
                else:
                    st.markdown(
                        '<p style="color:#16A34A;font-size:13px;margin-top:8px;">결측치 없음</p>',
                        unsafe_allow_html=True,
                    )

            # ── 문제 컬럼 카드 ────────────────────────────────────────────
            with col_issues:
                st.caption("주요 문제")
                unnamed_cnt = sum(1 for c in fi["col_names"] if "unnamed" in c.lower())
                seen: dict[str, int] = {}
                for c in fi["col_names"]:
                    seen[c] = seen.get(c, 0) + 1
                dup_cnt = sum(1 for v in seen.values() if v > 1)
                mixed_cnt = len(fi.get("mixed_type_cols", []))

                cards = []
                if unnamed_cnt:
                    cards.append(("Unnamed 컬럼", unnamed_cnt, "#FEF3C7", "#92400E"))
                if dup_cnt:
                    cards.append(("중복 컬럼명", dup_cnt, "#DBEAFE", "#1E40AF"))
                if mixed_cnt:
                    cards.append(("데이터 타입 불일치", mixed_cnt, "#FCE7F3", "#9D174D"))

                if cards:
                    for card_label, cnt, bg, fg in cards:
                        st.markdown(
                            f'<div style="background:{bg};color:{fg};padding:6px 12px;'
                            f'border-radius:6px;margin:4px 0;font-size:13px;">'
                            f'<b>{cnt}개</b>&nbsp; {card_label}</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(
                        '<p style="color:#16A34A;font-size:13px;margin-top:8px;">특이사항 없음</p>',
                        unsafe_allow_html=True,
                    )

            # ── 파일 현황 요약 ────────────────────────────────────────────
            with col_summary:
                st.caption("파일 현황")
                total_missing = sum(v for v in fi["null_counts"].values() if v > 0)
                num_col_cnt = sum(
                    1 for d in fi["dtypes"].values()
                    if "int" in d or "float" in d
                )
                st.metric("행수", f"{fi['rows']:,}")
                st.metric("결측치", f"{total_missing:,}")
                st.metric("수치형 컬럼", f"{num_col_cnt}개")
