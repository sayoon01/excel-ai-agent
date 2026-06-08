"""공통 사이드바 — 모델 선택, 파일 카운트, 채팅 컨트롤."""
from __future__ import annotations

import streamlit as st

from services.export import to_markdown
from services.file_manager import list_files, save_uploaded
from core.llm.llm_client import GEMINI_MODELS, OPENAI_MODELS, list_ollama_models
from core.chat_history import delete_chat, list_chats, save_chat, search_history
from ui.helpers import restore_chat, start_new_chat


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
                cid = start_new_chat()
                st.query_params["chat"] = cid
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

        # ── 세션 통계 ─────────────────────────────────────────────────────────
        _history = st.session_state.get("session_history")
        if _history is not None and _history.total() > 0:
            st.divider()
            _counts = _history.tool_counts()
            _chain  = _history.chain_str()
            _rate   = _history.success_rate()
            st.caption("📊 세션 통계")
            for lbl, cnt in _counts.items():
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'font-size:12px;padding:1px 0;">'
                    f'<span>{lbl}</span><span><b>{cnt}회</b></span></div>',
                    unsafe_allow_html=True,
                )
            if _chain:
                st.caption(f"체인: {_chain}")
            if _history.total() >= 3:
                st.caption(f"성공률: {_rate*100:.0f}%")

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
                            if restore_chat(chat["id"]):
                                st.query_params["chat"] = chat["id"]
                            st.rerun()
                with col_d:
                    if st.button("✕", key=f"del_chat_{chat['id']}", help="삭제"):
                        delete_chat(chat["id"])
                        if is_active:
                            cid = start_new_chat()
                            st.query_params["chat"] = cid
                        st.rerun()

        # ── 분석 히스토리 검색 ────────────────────────────────────────────────
        st.divider()
        with st.expander("🔍 분석 히스토리 검색"):
            _hist_q = st.text_input(
                "히스토리 검색",
                placeholder="합계, 필터, 병합...",
                key="history_search_query",
                label_visibility="collapsed",
            )
            if _hist_q and len(_hist_q.strip()) > 1:
                _hist_results = search_history(_hist_q.strip())
                if not _hist_results:
                    st.caption("검색 결과 없음")
                for _hi, _hr in enumerate(_hist_results):
                    _date = _hr["date"]
                    _date_fmt = f"{_date[4:6]}/{_date[6:8]}" if len(_date) >= 8 else ""
                    st.markdown(
                        f'<div style="font-size:11px;color:#888;margin-top:8px;">{_date_fmt}</div>'
                        f'<div style="font-size:13px;">{_hr["query"][:30]}</div>',
                        unsafe_allow_html=True,
                    )
                    _hc1, _hc2 = st.columns([3, 2])
                    with _hc1:
                        with st.expander("코드"):
                            st.code(_hr["code"][:400], language="python")
                    with _hc2:
                        if st.button("↩ 사용", key=f"hist_{_hi}", use_container_width=True):
                            st.session_state.pending_prompt = _hr["query"]
                            st.switch_page("pages/0_채팅.py")
