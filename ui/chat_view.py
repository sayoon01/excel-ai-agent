"""채팅 히스토리 렌더링, 코드 실행 컨트롤, 후속 질문 카드."""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from core.code_executor import execute
from services.file_manager import RESULT_DIR
from core.prompt_builder import _INTENT_LABEL
from ui.components import intent_badge_html, split_response


def extract_code_blocks(text: str) -> list[str]:
    return re.findall(r"```python\s*\n(.*?)```", text, re.DOTALL)


def render_code_controls(msg_idx: int, content: str) -> None:
    """코드 실행 버튼 또는 실행 결과를 렌더링."""
    exec_result = st.session_state.exec_results.get(msg_idx)

    if exec_result is not None:
        if exec_result.success:
            with st.container(border=True):
                rtype = exec_result.result_type
                if rtype == "dataframe" and exec_result.result_df is not None:
                    df = exec_result.result_df
                    row_h = min(400, max(120, len(df) * 35 + 40))
                    st.dataframe(df, use_container_width=True, height=row_h)
                elif rtype == "number" and exec_result.result_value is not None:
                    v = exec_result.result_value
                    fmt = f"{v:,.0f}" if isinstance(v, float) and v == int(v) else (
                        f"{v:,.2f}" if isinstance(v, float) else f"{v:,}"
                    )
                    st.metric(label="결과", value=fmt)
                elif rtype == "string" and exec_result.result_value is not None:
                    st.markdown(str(exec_result.result_value))
                if exec_result.output:
                    st.code(exec_result.output, language="text")
                for sfname in exec_result.saved_files:
                    fpath = RESULT_DIR / sfname
                    if fpath.exists():
                        st.download_button(
                            f"⬇ {sfname} 다운로드",
                            data=fpath.read_bytes(),
                            file_name=sfname,
                            key=f"dl_exec_{sfname}_{msg_idx}",
                        )
                st.caption("✓ 실행 완료")
        else:
            st.error(f"실행 오류:\n{exec_result.error}")
        return

    code_blocks = extract_code_blocks(content)
    if code_blocks:
        if st.button("▶ 코드 실행", key=f"exec_{msg_idx}"):
            with st.spinner("실행 중..."):
                result = execute(
                    code_blocks[0],
                    last_result=st.session_state.last_result,
                )
            st.session_state.exec_results[msg_idx] = result
            if result.success and result.result_df is not None:
                st.session_state.last_result = result.result_df
                st.session_state.result_history.append(result.result_df)
            st.rerun()


def render_follow_up_suggestions(suggestions: list[str]) -> None:
    if not suggestions:
        return
    st.markdown(
        '<p style="font-size:12px;color:#9CA3AF;margin:12px 0 6px 0;">'
        '다음 질문 추천</p>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(suggestions))
    key_base = len(st.session_state.messages)
    for i, (col, sug) in enumerate(zip(cols, suggestions)):
        with col:
            if st.button(sug, key=f"sugg_{key_base}_{i}", use_container_width=True):
                st.session_state.pending_prompt = sug
                st.rerun()


def render_chat_history() -> None:
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                display_content = msg.get("display", msg["content"])
                st.markdown(display_content)
                if msg.get("intent"):
                    label = _INTENT_LABEL.get(msg["intent"], msg["intent"])
                    st.markdown(
                        intent_badge_html(msg["intent"], label),
                        unsafe_allow_html=True,
                    )
            else:  # assistant
                narrative, code = split_response(msg["content"])
                st.markdown(narrative)
                if code:
                    with st.expander("코드 보기", expanded=False):
                        st.code(code, language="python")
                render_code_controls(idx, msg["content"])

    # 후속 질문 추천 카드 (마지막 어시스턴트 메시지 뒤)
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        last_idx = len(st.session_state.messages) - 1
        render_follow_up_suggestions(st.session_state.suggestions.get(last_idx, []))


def render_last_result_banner() -> None:
    _lr = st.session_state.last_result
    if _lr is None or not isinstance(_lr, pd.DataFrame):
        return
    cols_preview = ", ".join(_lr.columns.astype(str)[:5])
    if len(_lr.columns) > 5:
        cols_preview += f" +{len(_lr.columns) - 5}"
    col_banner, col_clear = st.columns([9, 1])
    with col_banner:
        st.markdown(
            f'<div style="background:#EFF6FF;border-left:3px solid #2563EB;'
            f'padding:8px 14px;border-radius:4px;font-size:13px;color:#1E40AF;">'
            f'⚡ <b>이전 결과</b> &nbsp;{len(_lr)}행 × {len(_lr.columns)}열'
            f'&nbsp;&nbsp;|&nbsp;&nbsp;{cols_preview}</div>',
            unsafe_allow_html=True,
        )
    with col_clear:
        if st.button("✕", key="clear_last_result", help="이전 결과 초기화"):
            st.session_state.last_result = None
            st.rerun()
