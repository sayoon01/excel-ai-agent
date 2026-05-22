"""공통 사이드바 — 모델 선택, 파일 카운트, 채팅 컨트롤."""
from __future__ import annotations

import streamlit as st

from services.export import to_markdown
from services.file_manager import list_files, save_uploaded
from core.llm_client import GEMINI_MODELS, OPENAI_MODELS, list_ollama_models
from core.chat_history import delete_chat, list_chats, load_chat, new_chat_id, save_chat


def render_sidebar() -> None:
    with st.sidebar:
        st.title("📊 Excel AI Platform")
        st.caption("엑셀/CSV 파일을 업로드하고 AI와 대화하세요")

        # ── AI 모델 설정 ──────────────────────────────────────────────────────
        st.subheader("AI 모델")

        provider = st.selectbox(
            "프로바이더",
            ["Ollama", "Gemini", "OpenAI"],
            index=["Ollama", "Gemini", "OpenAI"].index(st.session_state.provider),
            key="provider",
        )

        if provider == "Ollama":
            with st.spinner("모델 목록 조회 중..."):
                models = list_ollama_models(st.session_state.ollama_host)
            if models:
                st.selectbox("대화 모델", models, key="ollama_model")

                code_options = ["(대화 모델과 동일)"] + models
                cur_code = st.session_state.get("ollama_code_model", "")
                code_idx = (models.index(cur_code) + 1) if cur_code in models else 0
                chosen_code = st.selectbox("코드 모델", code_options, index=code_idx,
                                           help="필터·집계·변환·병합 요청에 사용. 비워두면 대화 모델 사용.")
                st.session_state.ollama_code_model = "" if chosen_code == "(대화 모델과 동일)" else chosen_code
            else:
                st.warning("Ollama 모델 없음. Ollama가 실행 중인지 확인하세요.")
                st.session_state.ollama_model = None

        elif provider == "Gemini":
            st.text_input("Gemini API 키", type="password", placeholder="AIza...", key="gemini_key")
            st.selectbox("모델", GEMINI_MODELS, key="gemini_model")

        elif provider == "OpenAI":
            st.text_input("OpenAI API 키", type="password", placeholder="sk-...", key="openai_key")
            st.selectbox("모델", OPENAI_MODELS, key="openai_model")

        st.divider()

        # ── 파일 업로드 ───────────────────────────────────────────────────────
        uploaded = st.file_uploader(
            "파일 업로드",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded:
            for f in uploaded:
                save_uploaded(f)
            st.cache_data.clear()
            st.rerun()

        files = list_files()
        if files:
            st.caption(f"📁 {len(files)}개 파일 업로드됨")
        else:
            st.caption("📁 파일을 업로드하세요 (xlsx / xls / csv)")

        st.divider()

        # ── 채팅 목록 ─────────────────────────────────────────────────────────
        col_new, col_exp = st.columns(2)
        with col_new:
            if st.button("새 대화", use_container_width=True):
                save_chat(st.session_state.current_chat_id, st.session_state.messages)
                st.session_state.messages = []
                st.session_state.exec_results = {}
                st.session_state.last_result = None
                st.session_state.result_history = []
                st.session_state.last_intent = None
                st.session_state.suggestions = {}
                st.session_state.current_chat_id = new_chat_id()
                st.rerun()
        with col_exp:
            if st.session_state.get("messages"):
                md = to_markdown(st.session_state.messages)
                st.download_button(
                    "내보내기",
                    data=md,
                    file_name="chat_export.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

        chats = list_chats()
        if chats:
            st.divider()
            st.caption("이전 대화")
            for chat in chats[:15]:
                is_active = chat["id"] == st.session_state.current_chat_id
                col_t, col_d = st.columns([5, 1])
                with col_t:
                    label = f"**{chat['title']}**" if is_active else chat["title"]
                    if st.button(label, key=f"chat_{chat['id']}", use_container_width=True):
                        if not is_active:
                            save_chat(st.session_state.current_chat_id, st.session_state.messages)
                            st.session_state.messages = load_chat(chat["id"])
                            st.session_state.current_chat_id = chat["id"]
                            st.session_state.exec_results = {}
                            st.session_state.last_result = None
                            st.session_state.suggestions = {}
                            st.rerun()
                with col_d:
                    if st.button("✕", key=f"del_chat_{chat['id']}", help="삭제"):
                        delete_chat(chat["id"])
                        if is_active:
                            st.session_state.messages = []
                            st.session_state.current_chat_id = new_chat_id()
                        st.rerun()
