"""채팅 히스토리 렌더링, 코드 실행 컨트롤, 후속 질문 카드."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from core.execution.code_executor import execute_with_retry
from services.file_manager import RESULT_DIR
from ui.components import split_response
from ui.helpers import get_llm_client
from ui.thinking_panel import render_thinking_panel
from ui.approval_panel import render_approval_panel


def extract_code_blocks(text: str) -> list[str]:
    return re.findall(r"```python\s*\n(.*?)```", text, re.DOTALL)


def _run_code(code: str, msg_idx: int) -> None:
    """코드 실행 + 결과 세션 저장."""
    client, _ = get_llm_client(force_code=True)

    original_question = ""
    if msg_idx > 0:
        prev = st.session_state.messages[msg_idx - 1]
        if prev["role"] == "user":
            original_question = prev.get("display", prev["content"])

    with st.spinner("실행 중... (오류 시 자동 수정)"):
        result = execute_with_retry(
            code,
            last_result=st.session_state.last_result,
            client=client,
            original_question=original_question,
            selected_sheets=st.session_state.get("selected_sheets", {}),
            selected_files=st.session_state.get("selected_files") or None,
        )
    st.session_state.exec_results[msg_idx] = result
    if result.success and result.result_df is not None:
        st.session_state.last_result = result.result_df
        st.session_state.result_history.append(result.result_df)
    # 세션 히스토리 기록
    _hist = st.session_state.get("session_history")
    if _hist is not None:
        from core.execution.pipeline import ToolExecution
        _rows = len(result.result_df) if result.result_df is not None else None
        _hist.record(ToolExecution(
            turn=msg_idx,
            mode="code",
            tool_name="",
            user_prompt=original_question[:60],
            success=result.success,
            duration_ms=0,
            result_rows=_rows,
            chained=False,
        ))
    st.rerun()


def render_code_controls(msg_idx: int, content: str) -> None:
    """코드 실행 버튼 또는 실행 결과를 렌더링."""
    exec_result = st.session_state.exec_results.get(msg_idx)

    if exec_result is not None:
        if exec_result.success:
            with st.container(border=True):
                rtype = exec_result.result_type
                if exec_result.result_df is not None:
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
                elif rtype == "plot" and exec_result.result_value:
                    chart_path = Path(str(exec_result.result_value))
                    if chart_path.exists():
                        st.image(str(chart_path), use_container_width=True)
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
                if (
                    exec_result.result_df is None
                    and not exec_result.saved_files
                    and exec_result.result_type not in ("number", "string", "plot")
                ):
                    st.info(
                        "실행은 완료됐지만 저장할 표(result)가 없습니다. "
                        "코드에 `result = ...`가 포함되어 있는지 확인한 뒤 다시 실행해 주세요."
                    )
                if exec_result.is_corrected:
                    label = f"↩ 자동 수정 {exec_result.correction_attempts}회 후 실행 완료"
                else:
                    label = "✓ 실행 완료"
                st.caption(label)
        else:
            st.error(f"실행 오류:\n{exec_result.error}")
        return

    # pipeline_states에 state가 있으면 승인 패널 사용
    state = st.session_state.pipeline_states.get(msg_idx)
    if state:
        # llm 모드는 코드 없음 — 승인 패널 불필요
        if state.mode == "llm" or not state.has_code:
            return
        action = render_approval_panel(state, msg_idx)
        if action in ("execute", "skip"):
            if action == "execute":
                _run_code(state.generated_code, msg_idx)
            else:
                st.caption("건너뛰었습니다.")
        return

    # pipeline_states 없는 과거 메시지 — 기존 단일 버튼 유지
    code_blocks = extract_code_blocks(content)
    if code_blocks:
        if st.button("▶ 코드 실행", key=f"exec_{msg_idx}"):
            _run_code(code_blocks[0], msg_idx)


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
            else:  # assistant
                narrative, code = split_response(msg["content"])
                st.markdown(narrative)
                if code:
                    with st.expander("코드 보기", expanded=False):
                        st.code(code, language="python")
                render_code_controls(idx, msg["content"])
                state = st.session_state.pipeline_states.get(idx)
                if state:
                    render_thinking_panel(state)

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
