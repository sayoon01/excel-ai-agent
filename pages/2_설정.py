"""설정 페이지 — Ollama 호스트, 디버그 프롬프트."""
from __future__ import annotations

import streamlit as st

from core.intent import INTENT_LABEL, detect_intent
from core.prompts.builder import augment_user_prompt, build_system_prompt
from services.file_manager import collect_files_info, list_files, read_file


st.header("설정")

# ── Ollama 호스트 ─────────────────────────────────────────────────────────────

if st.session_state.provider == "Ollama":
    st.subheader("Ollama 연결")
    st.text_input(
        "Ollama Host",
        value=st.session_state.ollama_host,
        key="ollama_host",
        help="Ollama 서버 주소 (기본값: http://localhost:11434)",
    )
    st.divider()

# ── 디버그: 프롬프트 미리보기 ─────────────────────────────────────────────────

st.subheader("프롬프트 디버그")
st.caption("실제로 LLM에 전송되는 시스템 프롬프트와 사용자 프롬프트를 확인합니다.")

debug_input = st.text_area(
    "테스트할 입력",
    placeholder="예: 매출 기준으로 필터해줘",
    height=80,
    key="debug_input",
)

if debug_input:
    _fi = collect_files_info(list_files())
    _intent = detect_intent(debug_input)

    st.caption(f"감지된 의도: **{INTENT_LABEL.get(_intent, _intent)}**")

    col_user, col_sys = st.columns(2)
    with col_user:
        st.markdown("**사용자 프롬프트 (보강 후)**")
        st.code(augment_user_prompt(debug_input, _fi), language="text")
    with col_sys:
        st.markdown("**시스템 프롬프트**")
        st.code(build_system_prompt(_fi, _intent), language="text")
