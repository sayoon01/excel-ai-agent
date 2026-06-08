"""채팅 히스토리 렌더링, 코드 실행 컨트롤, 후속 질문 카드."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from core.execution.code_executor import execute_with_retry
from services.file_manager import RESULT_DIR
from services.result_naming import download_label, result_filename
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

    # 성공 케이스를 RAG store에 추가 — 다음 유사 질문의 few-shot 예시로 활용
    if result.success and original_question and code:
        try:
            from core.rag.example_store import get_store
            from ui.helpers import get_embedder
            from ui.quality_report import load_files_info

            _state = st.session_state.pipeline_states.get(msg_idx)
            _intent = _state.intent if _state else "query"
            _selected = st.session_state.get("selected_files") or []
            if _selected:
                _fi = load_files_info(tuple(_selected))
                get_store().add(original_question, _intent, code, _fi)
        except Exception:
            pass

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
                            f"⬇ {download_label(sfname)}",
                            data=fpath.read_bytes(),
                            file_name=sfname,
                            mime=(
                                "image/png" if sfname.endswith(".png")
                                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            ),
                            key=f"dl_exec_{sfname}_{msg_idx}",
                        )
                # 디스크 저장 없이 표만 있는 경우 — 메모리에서 xlsx 생성해 다운로드 제공
                _has_xlsx = any(
                    f.endswith(".xlsx") for f in exec_result.saved_files
                )
                if exec_result.result_df is not None and not _has_xlsx:
                    _question = ""
                    if msg_idx > 0:
                        _prev = st.session_state.messages[msg_idx - 1]
                        if _prev["role"] == "user":
                            _question = _prev.get("display", _prev["content"])
                    _state = st.session_state.pipeline_states.get(msg_idx)
                    _intent = _state.intent if _state else ""
                    _dl_name = result_filename(prompt=_question, intent=_intent)
                    _buf = io.BytesIO()
                    exec_result.result_df.to_excel(_buf, index=False)
                    st.download_button(
                        f"⬇ {download_label(_dl_name)}",
                        data=_buf.getvalue(),
                        file_name=_dl_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_mem_{msg_idx}",
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


def _dsl_preview_to_df(preview: dict) -> "pd.DataFrame | None":
    if not preview or not isinstance(preview, dict):
        return None
    try:
        return pd.DataFrame(preview["rows"], columns=preview["columns"])
    except Exception:
        return None


def render_dsl_panel(msg_idx: int, dsl: dict) -> None:
    """기존 라우터 결과 아래에 DSL 라우터 결과를 별도 expander로 표시.

    intent에 따라 다른 정보 노출:
      - dsl: pipeline + 실행 결과(dataframe head 또는 plot)
      - text: message
      - ambiguous: message + suggested 후보 버튼
      - error: 에러 메시지 + suggestion
    """
    if not dsl or not isinstance(dsl, dict):
        return

    intent = dsl.get("intent", "?")
    rt_ms  = dsl.get("rt_ms", 0)
    exec_ms = dsl.get("exec_ms")
    badge_map = {
        "dsl":       ("🛠 DSL", "#0369A1", "#E0F2FE"),
        "text":      ("💬 분석 답변", "#15803D", "#F0FDF4"),
        "ambiguous": ("❓ 모호함", "#854D0E", "#FEF9C3"),
        "error":     ("⚠ 에러", "#B91C1C", "#FEE2E2"),
    }
    label, fg, bg = badge_map.get(intent, ("?", "#374151", "#F3F4F6"))
    timing = f" · 라우팅 {rt_ms}ms"
    if exec_ms is not None:
        timing += f" + 실행 {exec_ms}ms"

    title = f"🧪 DSL 라우터 결과 — {intent}{timing}"
    with st.expander(title, expanded=False):
        st.markdown(
            f'<span style="background:{bg};color:{fg};padding:3px 10px;'
            f'border-radius:6px;font-size:12px;">{label}</span>',
            unsafe_allow_html=True,
        )

        # 에러 / suggestion
        if dsl.get("error"):
            st.error(dsl["error"])
            if dsl.get("suggestion"):
                st.caption(f"💡 {dsl['suggestion']}")

        # text / ambiguous → message
        if intent in ("text", "ambiguous") and dsl.get("message"):
            st.markdown(dsl["message"])
        if intent == "ambiguous":
            sugg = dsl.get("suggested") or []
            if sugg:
                st.markdown("**구체화 제안**")
                for s in sugg[:5]:
                    st.markdown(f"- {s}")

        # dsl pipeline
        if dsl.get("explanation"):
            st.caption(f"의도 요약: {dsl['explanation']}")
        if dsl.get("pipeline"):
            with st.expander("DSL pipeline (JSON)", expanded=False):
                import json as _json
                st.code(_json.dumps(dsl["pipeline"], ensure_ascii=False, indent=2),
                        language="json")

        # 실행 결과
        if dsl.get("exec_ok") is True:
            t = dsl.get("exec_type")
            sm = dsl.get("exec_summary")
            if sm:
                st.caption(sm[:200])
            if t == "plot" and dsl.get("exec_path"):
                from pathlib import Path
                p = Path(dsl["exec_path"])
                if p.exists():
                    st.image(str(p), use_container_width=True)
            else:
                preview_df = _dsl_preview_to_df(dsl.get("exec_preview"))
                if preview_df is not None and not preview_df.empty:
                    shape = dsl.get("exec_preview", {}).get("shape")
                    cap = f"미리보기 (최대 50행 표시"
                    if shape:
                        cap += f", 전체 {shape[0]}행 × {shape[1]}컬럼"
                    cap += ")"
                    st.caption(cap)
                    h = min(400, max(120, len(preview_df) * 35 + 40))
                    st.dataframe(preview_df, use_container_width=True, height=h)
        elif dsl.get("exec_ok") is False:
            st.error(f"실행 실패: {dsl.get('exec_err', '')[:200]}")

        # step별 로그
        log = dsl.get("log")
        if log:
            with st.expander("step 실행 로그", expanded=False):
                for entry in log:
                    line = f"#{entry.get('step')} {entry.get('op')}"
                    if entry.get("shape"):
                        line += f" → shape {entry['shape']}"
                    if entry.get("error"):
                        line += f"  ✗ {entry['error']}"
                    st.text(line)


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
                # DSL 라우터 비교 결과 (shadow mode)
                dsl = st.session_state.dsl_results.get(idx) or (
                    msg.get("dsl_result") if isinstance(msg, dict) else None
                )
                if dsl:
                    render_dsl_panel(idx, dsl)

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
