"""코드 실행 전 승인 UI — [실행] [수정] [건너뛰기]."""
from __future__ import annotations

import streamlit as st

from core.pipeline import PipelineState


def render_approval_panel(state: PipelineState, msg_idx: int) -> str | None:
    """
    코드 실행 승인 UI.

    반환값:
        "execute" — 실행 승인 (수정된 코드면 state.generated_code가 업데이트됨)
        "skip"    — 건너뛰기
        None      — 아직 선택 안 함
    """
    if not state.has_code:
        return None

    edit_key = f"approval_editing_{msg_idx}"

    st.divider()

    if st.session_state.get(edit_key):
        # 수정 모드
        edited = st.text_area(
            "코드 수정",
            value=state.generated_code,
            height=220,
            key=f"code_editor_{msg_idx}",
        )
        ec1, ec2 = st.columns([2, 1])
        with ec1:
            if st.button("▶ 수정된 코드 실행", key=f"run_edited_{msg_idx}", type="primary"):
                state.generated_code = edited
                st.session_state[edit_key] = False
                return "execute"
        with ec2:
            if st.button("취소", key=f"cancel_edit_{msg_idx}"):
                st.session_state[edit_key] = False
                st.rerun()
        return None

    # 일반 승인 버튼
    col1, col2, col3, col_info = st.columns([2, 1, 1, 3])
    with col1:
        if st.button("▶ 코드 실행", key=f"approve_{msg_idx}", type="primary"):
            return "execute"
    with col2:
        if st.button("✏️ 수정", key=f"edit_{msg_idx}"):
            st.session_state[edit_key] = True
            st.rerun()
    with col3:
        if st.button("건너뛰기", key=f"skip_{msg_idx}"):
            return "skip"
    with col_info:
        st.caption("샌드박스 실행 · import/파일I/O 차단 · 30초 제한")

    return None
